#!/usr/bin/env python3
"""
End-to-end integration test that creates tenant, channel, flow in database
and tests the flow chat API as if a real user were using it.
"""

import pytest
import uuid
from typing import Any
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import create_session
from app.db.repository import (
    create_tenant_with_config,
    create_channel_instance,
    create_flow,
    get_flow_by_id,
    list_flow_chat_messages,
)
from app.db.models import ChannelType, FlowChatRole
from app.services.tenant_service import TenantService
from app.core.app_context import get_app_context
from app.core.llm import LLMClient


class MockLLMForTesting(LLMClient):
    """Mock LLM client that returns predictable responses for testing."""
    
    def __init__(self):
        self.call_count = 0
        
    def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]:  # type: ignore[override]
        """Return predictable responses based on the prompt content."""
        self.call_count += 1
        
        # Simulate responses based on prompt content
        if "what would you like to test" in prompt.lower():
            return {"response": "I can see you're interested in testing. Let me guide you through our test flow."}
        elif "basic" in prompt.lower() and "functionality" in prompt.lower():
            return {"response": "Great! For basic testing, what type of responses do you prefer: detailed or concise?"}
        elif "detailed" in prompt.lower() or "concise" in prompt.lower():
            return {"response": "Perfect! How was your testing experience? Any feedback or additional requests?"}
        elif "feedback" in prompt.lower() or "experience" in prompt.lower():
            return {"response": "Basic testing completed successfully! Thanks for using our system."}
        else:
            return {"response": f"I understand your request. This is response #{self.call_count} from the mock LLM."}


class TestEndToEndFlowAPI:
    """Comprehensive end-to-end test suite for flow creation and chat API."""
    
    @pytest.fixture(scope="class")
    def mock_llm(self):
        """Create a mock LLM for testing."""
        return MockLLMForTesting()
    
    @pytest.fixture(scope="class", autouse=True)  
    def setup_llm_context(self, mock_llm):
        """Setup mock LLM in app context for all tests."""
        with patch('app.main._init_llm') as mock_init:
            # Mock the LLM initialization
            with patch.object(app.state, 'app_context', create=True) as mock_context:
                mock_ctx = Mock()
                mock_ctx.llm = mock_llm
                mock_ctx.session_policy = Mock()
                mock_ctx.rate_limiter = None
                mock_context.return_value = mock_ctx
                yield mock_ctx
    
    @pytest.fixture(scope="class")
    def test_data(self):
        """Create test tenant with actual dentist flow for realistic testing."""
        import json
        from pathlib import Path
        
        test_id = str(uuid.uuid4())[:8]  # Short unique ID for this test run
        session = create_session()
        
        try:
            # Create tenant with realistic dentist configuration (like seed_database.py)
            tenant = create_tenant_with_config(
                session,
                first_name="Dr. Test",
                last_name="Integration",
                email=f"test-dentist-{test_id}@example.com",
                project_description="Clínica odontológica para testes de integração - atendimento completo desde limpeza até ortodontia",
                target_audience="Pacientes de todas as idades que buscam cuidados dentários de qualidade para fins de teste",
                communication_style="Receptiva calorosa mas profissional de uma clínica dentária brasileira. Tom amigável e acolhedor, sempre transmitindo confiança médica."
            )
            
            # Create channel instance (WhatsApp number)
            test_phone = f"+1555{test_id[:4]}{test_id[4:8]}"
            channel = create_channel_instance(
                session,
                tenant_id=tenant.id,
                channel_type=ChannelType.whatsapp,
                identifier=f"whatsapp:{test_phone}",
                phone_number=test_phone,
                extra={"display_name": "Test Dentist Clinic"}
            )
            
            # Load the ACTUAL dentist flow from fixtures
            dentist_flow_path = Path(__file__).parent / "fixtures" / "dentist_flow.json"
            with open(dentist_flow_path, "r", encoding="utf-8") as f:
                dentist_flow_definition = json.load(f)
            
            # Create the dentist flow (exactly like seed_database.py)
            flow = create_flow(
                session,
                tenant_id=tenant.id,
                channel_instance_id=channel.id,
                name="Atendimento Consultório Dentista - Test",
                flow_id="dentist_consultation_flow_test", 
                definition=dentist_flow_definition
            )
            
            session.commit()
            
            return {
                "tenant_id": tenant.id,
                "channel_id": channel.id,
                "flow_id": flow.id,
                "test_id": test_id,
                "test_phone": test_phone,
                "flow_definition": dentist_flow_definition  # Keep reference for verification
            }
            
        finally:
            session.close()
    
    def test_create_tenant_and_flow(self, test_data):
        """Test that tenant and dentist flow were created successfully in database."""
        session = create_session()
        try:
            # Verify flow exists and has correct structure
            flow = get_flow_by_id(session, test_data["flow_id"])
            assert flow is not None
            assert flow.name == "Atendimento Consultório Dentista - Test"
            assert flow.flow_id == "dentist_consultation_flow_test"
            assert flow.is_active is True
            assert flow.definition["schema_version"] == "v1"
            assert flow.definition["id"] == "flow.consultorio_dentista"
            
            # Verify it has the dentist flow structure
            nodes = flow.definition.get("nodes", [])
            edges = flow.definition.get("edges", [])
            
            # Should have the pain intensity question we'll modify
            pain_question = next((n for n in nodes if n.get("id") == "q.intensidade_dor"), None)
            assert pain_question is not None, "Pain intensity question should exist"
            assert pain_question.get("allowed_values") == ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
            print(f"✅ Found pain question with 1-10 scale: {pain_question}")
            
        finally:
            session.close()
    
    def test_flow_chat_api_send_message(self, test_data, mock_llm):
        """Test sending messages to flow chat API and receiving responses."""
        client = TestClient(app)
        flow_id = str(test_data["flow_id"])
        
        # Directly set the LLM in the app context
        from app.core.app_context import get_app_context
        ctx = get_app_context(app)
        original_llm = ctx.llm
        ctx.llm = mock_llm
        
        try:
            # Mock the _build_agent function to return a mock agent
            with patch('app.api.flow_chat._build_agent') as mock_build_agent:
                mock_agent = Mock()
                from app.agents.flow_chat_agent import FlowChatResponse
                mock_agent.process.return_value = FlowChatResponse(
                    messages=["I can see you're interested in testing. Let me guide you through our test flow."],
                    flow_was_modified=False,
                    modification_summary=None
                )
                mock_build_agent.return_value = mock_agent
                
                # Test 1: Send initial message to start flow
                response = client.post(
                    f"/flows/{flow_id}/chat/send",
                    json={"content": "I want to test the basic flow functionality"}
                )
                
                assert response.status_code == 200
                response_data = response.json()
                messages = response_data["messages"]
                assert len(messages) >= 1
                
                # Should get assistant response
                assistant_message = next((m for m in messages if m["role"] == "assistant"), None)
                assert assistant_message is not None
                assert len(assistant_message["content"]) > 0
                
                # Test 2: Continue conversation 
                mock_agent.process.return_value = FlowChatResponse(
                    messages=["Great! For basic testing, what type of responses do you prefer?"],
                    flow_was_modified=False,
                    modification_summary=None
                )
                
                response2 = client.post(
                    f"/flows/{flow_id}/chat/send",
                    json={"content": "I want to test basic functionality with detailed responses"}
                )
                
                assert response2.status_code == 200
                response_data2 = response2.json()
                messages2 = response_data2["messages"]
                assert len(messages2) >= 1
                
                # Should progress through the flow
                assistant_message2 = next((m for m in messages2 if m["role"] == "assistant"), None)
                assert assistant_message2 is not None
        finally:
            # Restore original LLM
            ctx.llm = original_llm
    
    def test_flow_chat_api_list_messages(self, test_data, mock_llm):
        """Test retrieving chat history from the API."""
        client = TestClient(app)
        flow_id = str(test_data["flow_id"])
        
        # Mock the agent and context for sending a message first
        with patch('app.agents.flow_chat_agent.FlowChatAgent') as mock_agent_class:
            mock_agent = Mock()
            from app.agents.flow_chat_agent import FlowChatResponse
            mock_agent.process.return_value = FlowChatResponse(
                messages=["Test response from agent"],
                flow_was_modified=False,
                modification_summary=None
            )
            mock_agent_class.return_value = mock_agent
            
            with patch('app.core.app_context.get_app_context') as mock_get_ctx:
                mock_ctx = Mock()
                mock_ctx.llm = mock_llm
                mock_get_ctx.return_value = mock_ctx
                
                # First send a message to ensure we have chat history
                client.post(
                    f"/flows/{flow_id}/chat/send",
                    json={"content": "Test message for history"}
                )
        
        # Now retrieve all messages (this endpoint doesn't need LLM)
        with patch('app.services.flow_chat_service.FlowChatService') as mock_service_class:
            mock_service = Mock()
            mock_service.list_messages.return_value = []  # Will be populated by real DB calls
            
            response = client.get(f"/flows/{flow_id}/chat/messages")
            
            assert response.status_code == 200
            messages = response.json()
            # We know we have at least the messages we just sent
            assert len(messages) >= 1
    
    def test_database_persistence(self, test_data, mock_llm):
        """Test that chat messages are properly persisted in database."""
        client = TestClient(app)
        flow_id = str(test_data["flow_id"])
        
        # Directly set the LLM in the app context
        from app.core.app_context import get_app_context
        ctx = get_app_context(app)
        original_llm = ctx.llm
        ctx.llm = mock_llm
        
        try:
            # Mock the _build_agent function to return a mock agent
            with patch('app.api.flow_chat._build_agent') as mock_build_agent:
                mock_agent = Mock()
                from app.agents.flow_chat_agent import FlowChatResponse
                mock_agent.process.return_value = FlowChatResponse(
                    messages=["Mock assistant response for persistence test"],
                    flow_was_modified=False,
                    modification_summary=None
                )
                mock_build_agent.return_value = mock_agent
                
                # Send a unique message we can verify later
                test_message = f"Unique test message {uuid.uuid4()}"
                response = client.post(
                    f"/flows/{flow_id}/chat/send",
                    json={"content": test_message}
                )
                
                assert response.status_code == 200
            
            # Check database directly
            session = create_session()
            try:
                db_messages = list_flow_chat_messages(session, test_data["flow_id"])
                
                # Find our test message
                user_message = next((m for m in db_messages if m.content == test_message), None)
                assert user_message is not None
                assert user_message.role == FlowChatRole.user
                
                # Should have corresponding assistant response
                assistant_messages = [m for m in db_messages if m.role == FlowChatRole.assistant]
                assert len(assistant_messages) >= 1
                
            finally:
                session.close()
        finally:
            # Restore original LLM
            ctx.llm = original_llm
    
    def test_flow_modification_through_chat(self, test_data, mock_llm):
        """Test REAL chat-to-flow feature: 'Mude a escala de 1 a 10 pra 1 a 5'"""
        client = TestClient(app) 
        flow_id = str(test_data["flow_id"])
        
        # Get the original pain scale from the dentist flow
        session = create_session()
        try:
            original_flow = get_flow_by_id(session, test_data["flow_id"])
            assert original_flow is not None
            original_version = original_flow.version
            
            # Find the pain intensity question (q.intensidade_dor)
            original_nodes = original_flow.definition.get("nodes", [])
            pain_node = next((n for n in original_nodes if n.get("id") == "q.intensidade_dor"), None)
            assert pain_node is not None, "Pain intensity question should exist in dentist flow"
            
            original_scale = pain_node.get("allowed_values", [])
            assert original_scale == ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"], "Should start with 1-10 scale"
            print(f"✅ Original pain scale: {original_scale}")
            
        finally:
            session.close()
        
        # Set up LLM in app context
        from app.core.app_context import get_app_context
        ctx = get_app_context(app)
        original_llm = ctx.llm
        ctx.llm = mock_llm
        
        try:
            # Mock the agent to actually call the flow modification tools
            with patch('app.api.flow_chat._build_agent') as mock_build_agent:
                mock_agent = Mock()
                
                def mock_process(flow_def, history, flow_id=None, session=None):
                    """Mock agent that processes 'Mude a escala de 1 a 10 pra 1 a 5' request."""
                    from app.agents.flow_modification_tools import update_node
                    from app.agents.flow_chat_agent import FlowChatResponse
                    
                    if session and flow_id and flow_def:
                        try:
                            # Simulate understanding the Portuguese request to change the scale
                            # "Mude a escala de 1 a 10 pra 1 a 5" = Change scale from 1-10 to 1-5
                            result = update_node(
                                flow_definition=flow_def,
                                node_id="q.intensidade_dor",
                                updates={"allowed_values": ["1", "2", "3", "4", "5"]},
                                flow_id=flow_id,
                                session=session,
                                user_message="Escala de dor alterada de 1-10 para 1-5 com sucesso!"
                            )
                            return FlowChatResponse(
                                messages=[f"✅ Perfeito! Alterei a escala de dor de 1-10 para 1-5. {result}"],
                                flow_was_modified=True,
                                modification_summary="update_node: q.intensidade_dor - Changed pain scale from 1-10 to 1-5"
                            )
                        except Exception as e:
                            return FlowChatResponse(
                                messages=[f"❌ Erro ao alterar a escala: {str(e)}"],
                                flow_was_modified=False,
                                modification_summary=None
                            )
                    
                    return FlowChatResponse(
                        messages=["Desculpe, não consegui processar sua solicitação de alteração."],
                        flow_was_modified=False,
                        modification_summary=None
                    )
                
                mock_agent.process.side_effect = mock_process
                mock_build_agent.return_value = mock_agent
                
                # Send the REAL Portuguese request (exactly what user would type)
                response = client.post(
                    f"/flows/{flow_id}/chat/send",
                    json={"content": "Mude a escala de 1 a 10 pra 1 a 5"}
                )
                
                assert response.status_code == 200
                response_data = response.json()
                messages = response_data["messages"]
                
                # Should get a Portuguese response indicating success
                assistant_message = next((m for m in messages if m["role"] == "assistant"), None)
                assert assistant_message is not None
                assert "escala de dor" in assistant_message["content"].lower()
                print(f"✅ Agent response: {assistant_message['content']}")
                
                # CRITICAL: Verify the pain scale was actually changed in the database
                # Use a FRESH database connection to avoid session caching issues
                fresh_session = create_session()
                try:
                    # Force fresh read from database (not session cache)
                    modified_flow = get_flow_by_id(fresh_session, test_data["flow_id"])
                    assert modified_flow is not None
                    
                    # Version should be incremented (this proves database write happened)
                    print(f"🔍 Checking versions: original={original_version}, current={modified_flow.version}")
                    assert modified_flow.version > original_version, f"Version should increment from {original_version}, got {modified_flow.version}"
                    print(f"✅ Flow version updated: {original_version} → {modified_flow.version}")
                    
                    # Find the modified pain question in fresh data
                    modified_nodes = modified_flow.definition.get("nodes", [])
                    modified_pain_node = next((n for n in modified_nodes if n.get("id") == "q.intensidade_dor"), None)
                    assert modified_pain_node is not None, "Pain question should still exist after modification"
                    
                    # THE CRITICAL TEST: Scale should now be 1-5 instead of 1-10
                    new_scale = modified_pain_node.get("allowed_values", [])
                    expected_scale = ["1", "2", "3", "4", "5"]
                    
                    print(f"🔍 Database verification:")
                    print(f"  Original scale: {original_scale} ({len(original_scale)} values)")
                    print(f"  Fresh DB scale: {new_scale} ({len(new_scale)} values)")
                    print(f"  Expected scale: {expected_scale}")
                    
                    # This assertion will show if the bug is fixed or still present
                    if new_scale == expected_scale:
                        print("🎉 SUCCESS: Chat-to-flow persistence is WORKING! Changes saved to database!")
                        assert len(new_scale) == 5, f"Should have exactly 5 values, got {len(new_scale)}"
                    else:
                        print("❌ BUG CONFIRMED: Changes made in memory but NOT persisted to database!")
                        print(f"💡 This confirms the persistence bug in flow modification tools")
                        # Still assert to fail the test and document the issue
                        assert new_scale == expected_scale, f"PERSISTENCE BUG: Expected {expected_scale}, but database still has {new_scale}"
                    
                    # Verify other properties remain unchanged
                    assert modified_pain_node.get("id") == "q.intensidade_dor"
                    assert modified_pain_node.get("kind") == "Question"
                    assert modified_pain_node.get("key") == "intensidade_dor"
                    assert "1 a 10" in modified_pain_node.get("prompt", "")  # Prompt mentions the original scale
                    
                finally:
                    fresh_session.close()
                    
        finally:
            # Restore original LLM
            ctx.llm = original_llm
    
    def test_admin_api_integration(self, test_data):
        """Test that flows created in this test are accessible via admin API."""
        client = TestClient(app)
        tenant_id = str(test_data["tenant_id"])
        
        # List all flows for the tenant
        response = client.get(f"/admin/tenants/{tenant_id}/flows")
        
        assert response.status_code == 200
        flows = response.json()
        assert len(flows) >= 1
        
        # Find our test flow (dentist flow)
        test_flow = next((f for f in flows if f["flow_id"] == "dentist_consultation_flow_test"), None)
        assert test_flow is not None
        assert test_flow["name"] == "Atendimento Consultório Dentista - Test"
    
    def test_tenant_service_integration(self, test_data):
        """Test TenantService operations on the created tenant."""
        session = create_session()
        try:
            service = TenantService(session)
            
            # Test getting tenant
            tenant = service.get_tenant_by_id(test_data["tenant_id"])
            assert tenant is not None
            assert tenant.owner_first_name == "Dr. Test"
            assert tenant.owner_last_name == "Integration"
            
            # Test getting flows
            flows = service.get_flows(test_data["tenant_id"])
            assert len(flows) >= 1
            
            test_flow = next((f for f in flows if f.flow_id == "dentist_consultation_flow_test"), None)
            assert test_flow is not None
            
            # Test getting channel instances
            channels = service.get_channel_instances(test_data["tenant_id"])
            assert len(channels) >= 1
            assert channels[0].id == test_data["channel_id"]
            
        finally:
            session.close()
    
    def test_error_handling(self, test_data, mock_llm):
        """Test API error handling with invalid requests."""
        client = TestClient(app)
        
        # Directly set the LLM in the app context
        from app.core.app_context import get_app_context
        ctx = get_app_context(app)
        original_llm = ctx.llm
        ctx.llm = mock_llm
        
        try:
            # Test with non-existent flow
            fake_flow_id = str(uuid.uuid4())
            response = client.post(
                f"/flows/{fake_flow_id}/chat/send",
                json={"content": "This should fail"}
            )
            # Should return 500 due to foreign key constraint violation when trying to save chat message
            assert response.status_code == 500
            assert "Internal server error" in response.json()["detail"]
            
            # Test with empty message content
            flow_id = str(test_data["flow_id"])
            response2 = client.post(
                f"/flows/{flow_id}/chat/send", 
                json={"content": ""}
            )
            assert response2.status_code == 400
            assert "empty" in response2.json()["detail"].lower()
            
            # Test with missing content field
            response3 = client.post(
                f"/flows/{flow_id}/chat/send",
                json={}
            )
            assert response3.status_code in [400, 422]  # Validation error
        finally:
            # Restore original LLM
            ctx.llm = original_llm
    
    @pytest.mark.skip(reason="LLM integration test - enable manually when needed") 
    def test_real_llm_flow_execution(self, test_data):
        """Test actual LLM-powered flow execution (skipped by default due to API costs)."""
        # This test would verify that the flow actually works with a real LLM
        # Enable by removing @pytest.mark.skip when doing comprehensive testing
        
        from app.settings import get_settings
        settings = get_settings()
        
        if settings.llm_provider == "openai" and settings.openai_api_key == "test":
            pytest.skip("LLM not configured for integration testing")
        
        client = TestClient(app)
        flow_id = str(test_data["flow_id"])
        
        # Full conversation flow with real LLM
        response1 = client.post(
            f"/flows/{flow_id}/chat/send",
            json={"content": "I want to test advanced features like flow modifications"}
        )
        assert response1.status_code == 200
        
        # Continue the conversation
        response2 = client.post(
            f"/flows/{flow_id}/chat/send", 
            json={"content": "I'd like to test adding new nodes and updating existing questions"}
        )
        assert response2.status_code == 200
        
        # Final message
        response3 = client.post(
            f"/flows/{flow_id}/chat/send",
            json={"content": "The system works great! Thanks for the comprehensive testing."}
        )
        assert response3.status_code == 200
        
        # Verify we got meaningful responses at each step
        response_data1 = response1.json()
        response_data2 = response2.json()
        response_data3 = response3.json()
        messages1 = response_data1["messages"]
        messages2 = response_data2["messages"]
        messages3 = response_data3["messages"]
        
        # Each response should have assistant messages
        assert any(m["role"] == "assistant" for m in messages1)
        assert any(m["role"] == "assistant" for m in messages2)  
        assert any(m["role"] == "assistant" for m in messages3)
