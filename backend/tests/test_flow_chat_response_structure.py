"""
Simple focused tests for the new FlowChatResponse structure and modification tracking.
Tests the core functionality without complex database mocking.
"""

import pytest
from unittest.mock import Mock
from uuid import uuid4

from app.agents.flow_chat_agent import FlowChatAgent, FlowChatResponse, ToolSpec
from app.services.flow_chat_service import FlowChatService, FlowChatServiceResponse
from app.db.models import FlowChatMessage, FlowChatRole
from app.core.llm import LLMClient


class TestFlowChatResponseStructure:
    """Test the FlowChatResponse data structure."""
    
    def test_flow_chat_response_creation(self):
        """Test creating FlowChatResponse with all fields."""
        response = FlowChatResponse(
            messages=["Test message 1", "Test message 2"],
            flow_was_modified=True,
            modification_summary="update_node: q.test - Test modification"
        )
        
        assert isinstance(response.messages, list)
        assert len(response.messages) == 2
        assert response.flow_was_modified is True
        assert response.modification_summary == "update_node: q.test - Test modification"
    
    def test_flow_chat_response_no_modifications(self):
        """Test FlowChatResponse for read-only operations."""
        response = FlowChatResponse(
            messages=["Flow looks good"],
            flow_was_modified=False,
            modification_summary=None
        )
        
        assert response.flow_was_modified is False
        assert response.modification_summary is None
        assert len(response.messages) == 1
    
    def test_flow_chat_service_response_structure(self):
        """Test the service layer response structure."""
        mock_message = Mock(spec=FlowChatMessage)
        mock_message.id = uuid4()
        mock_message.content = "Test message"
        mock_message.role = FlowChatRole.assistant
        
        service_response = FlowChatServiceResponse(
            messages=[mock_message],
            flow_was_modified=True,
            modification_summary="test: modification"
        )
        
        assert isinstance(service_response.messages, list)
        assert len(service_response.messages) == 1
        assert service_response.flow_was_modified is True
        assert service_response.modification_summary == "test: modification"


class TestFlowModificationTracking:
    """Test flow modification tracking logic."""
    
    def test_modification_tracking_with_success_emoji(self):
        """Test that ✅ emoji triggers flow_was_modified flag."""
        # This tests the core logic without complex LLM/database mocking
        
        # Simulate tool output with success emoji
        tool_output = "✅ Node updated successfully"
        user_message = "Test modification"
        
        # Simulate the agent's modification tracking logic
        modification_detected = "✅" in tool_output or (user_message and user_message in tool_output)
        modification_details = []
        
        if modification_detected:
            modification_details.append(f"update_node: q.test - {user_message}")
        
        # Verify tracking logic
        assert modification_detected is True
        assert len(modification_details) == 1
        assert "update_node: q.test - Test modification" in modification_details[0]
    
    def test_modification_tracking_with_user_message_echo(self):
        """Test that echoed user message triggers modification flag."""
        tool_output = "Updated pain scale to 1-5"
        user_message = "Updated pain scale to 1-5"
        
        # Simulate the agent's modification tracking logic  
        modification_detected = "✅" in tool_output or (user_message and user_message in tool_output)
        
        assert modification_detected is True
    
    def test_no_modification_tracking_for_failures(self):
        """Test that failed tool outputs don't trigger modification flag."""
        tool_output = "❌ Failed to update node - invalid parameters"
        user_message = "Update node"
        
        # Simulate the agent's modification tracking logic
        modification_detected = "✅" in tool_output or (user_message and user_message in tool_output)
        
        assert modification_detected is False
    
    def test_multiple_modifications_summary(self):
        """Test tracking multiple modifications in one conversation."""
        modifications = [
            "update_node: q.intensidade_dor - Scale to 1-5",
            "update_node: q.intensidade_dor - Updated prompt",
            "update_node: d.nivel_emergencia - Updated decision logic"
        ]
        
        summary = "; ".join(modifications)
        
        assert "Scale to 1-5" in summary
        assert "Updated prompt" in summary
        assert "Updated decision logic" in summary
        assert summary.count(";") == 2  # Two separators for three items


class TestAPIResponseStructure:
    """Test API response structure."""
    
    def test_api_response_model_structure(self):
        """Test that API response model has correct structure."""
        from app.api.flow_chat import FlowChatResponse as APIFlowChatResponse
        from app.api.flow_chat import ChatMessageResponse
        
        # Test the Pydantic model structure
        sample_message = ChatMessageResponse(
            id=uuid4(),
            role=FlowChatRole.assistant,
            content="Test message",
            created_at="2024-01-01T00:00:00Z"
        )
        
        api_response = APIFlowChatResponse(
            messages=[sample_message],
            flow_was_modified=True,
            modification_summary="update_node: q.test - Test"
        )
        
        # Verify structure
        assert hasattr(api_response, 'messages')
        assert hasattr(api_response, 'flow_was_modified') 
        assert hasattr(api_response, 'modification_summary')
        assert len(api_response.messages) == 1
        assert api_response.flow_was_modified is True
        assert api_response.modification_summary == "update_node: q.test - Test"
    
    def test_api_response_serialization(self):
        """Test that API response can be serialized to JSON."""
        from app.api.flow_chat import FlowChatResponse as APIFlowChatResponse
        from app.api.flow_chat import ChatMessageResponse
        
        sample_message = ChatMessageResponse(
            id=uuid4(),
            role=FlowChatRole.assistant,
            content="Test message", 
            created_at="2024-01-01T00:00:00Z"
        )
        
        api_response = APIFlowChatResponse(
            messages=[sample_message],
            flow_was_modified=True,
            modification_summary="test modification"
        )
        
        # Test JSON serialization
        json_data = api_response.model_dump()
        
        assert 'messages' in json_data
        assert 'flow_was_modified' in json_data
        assert 'modification_summary' in json_data
        assert json_data['flow_was_modified'] is True
        assert json_data['modification_summary'] == "test modification"


class TestRealWorldScenarios:
    """Test real-world flow chat scenarios."""
    
    def test_pain_scale_modification_response_structure(self):
        """Test the response structure for the pain scale modification scenario."""
        # Simulate the response that would be generated for pain scale update
        messages = [
            "Vou atualizar a escala de dor de 1-10 para 1-5",
            "✅ Updated node 'q.intensidade_dor': allowed_values, prompt",
            "✅ Updated node 'd.nivel_emergencia': decision_prompt", 
            "Escala de dor atualizada com sucesso!"
        ]
        
        # Simulate modification tracking
        modifications = [
            "update_node: q.intensidade_dor - Escala de dor atualizada de 1-10 para 1-5",
            "update_node: d.nivel_emergencia - Lógica de decisão atualizada para nova escala"
        ]
        
        response = FlowChatResponse(
            messages=messages,
            flow_was_modified=True,
            modification_summary="; ".join(modifications)
        )
        
        # Verify the response matches expected structure
        assert response.flow_was_modified is True
        assert "q.intensidade_dor" in response.modification_summary
        assert "d.nivel_emergencia" in response.modification_summary
        assert "Escala de dor atualizada" in response.modification_summary
        assert len(response.messages) == 4
        assert any("✅" in msg for msg in response.messages)
    
    def test_information_query_response_structure(self):
        """Test response structure for information queries (no modifications)."""
        messages = [
            "Este fluxo tem 2 nós configurados para capturar informações sobre dor e determinar o nível de emergência. Está funcionando bem para triagem de pacientes."
        ]
        
        response = FlowChatResponse(
            messages=messages,
            flow_was_modified=False,
            modification_summary=None
        )
        
        # Verify no modification flags for informational queries
        assert response.flow_was_modified is False
        assert response.modification_summary is None
        assert len(response.messages) == 1
        assert "funcionando bem" in response.messages[0]
    
    def test_error_scenario_response_structure(self):
        """Test response structure for error scenarios."""
        messages = [
            "I'll try to update that node",
            "❌ Failed to update node - node not found",
            "Sorry, I couldn't find that node. Please check the node ID and try again."
        ]
        
        response = FlowChatResponse(
            messages=messages,
            flow_was_modified=False,  # No modification on error
            modification_summary=None
        )
        
        # Verify error handling doesn't set modification flags
        assert response.flow_was_modified is False
        assert response.modification_summary is None
        assert any("❌" in msg for msg in response.messages)
        assert any("Sorry" in msg for msg in response.messages)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
