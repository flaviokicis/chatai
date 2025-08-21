"""
Focused integration tests for specific flow tools using real LLM calls.

These tests focus on individual tool functionality to provide comprehensive coverage
without hitting API rate limits as much as the full flow test.
"""

import os
import pytest
import time
from typing import Any, Dict, List

from langchain.chat_models import init_chat_model

from app.core.langchain_adapter import LangChainToolsLLM
from app.flow_core.compiler import FlowCompiler
from app.flow_core.runner import FlowTurnRunner
from app.flow_core.state import FlowContext
from app.flow_core.ir import (
    Flow, FlowMetadata, QuestionNode, DecisionNode, TerminalNode, Edge, GuardRef
)


def rate_limit_delay():
    """Add delay to avoid hitting API rate limits."""
    time.sleep(1.0)


@pytest.fixture(scope="module")
def real_llm():
    """Create a real LLM client for integration testing."""
    # Skip if no API key available
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or api_key == "test":
        pytest.skip("GOOGLE_API_KEY not configured - skipping LLM integration tests")
    
    # Use a fast, cost-effective model for testing
    chat = init_chat_model("gemini-2.5-flash-lite", model_provider="google_genai")
    return LangChainToolsLLM(chat)


@pytest.fixture
def path_correction_flow():
    """Create a simple flow for testing path corrections."""
    return Flow(
        id="path_correction_test",
        metadata=FlowMetadata(name="Path Correction Test"),
        entry="start",
        nodes=[
            DecisionNode(id="start"),
            QuestionNode(
                id="q_intent",
                key="user_intent",
                prompt="O que você gostaria de fazer hoje?",
                priority=10,
            ),
            DecisionNode(
                id="d_route",
                decision_type="llm_assisted",
                decision_prompt="Qual caminho devemos seguir?"
            ),
            QuestionNode(
                id="q_support_issue",
                key="support_issue",
                prompt="Que problema técnico você está enfrentando?",
                priority=20,
            ),
            QuestionNode(
                id="q_product_interest", 
                key="product_interest",
                prompt="Qual categoria de produto te interessa?",
                priority=20,
            ),
            TerminalNode(id="support_done", reason="Suporte concluído"),
            TerminalNode(id="sales_done", reason="Vendas concluídas"),
        ],
        edges=[
            Edge(source="start", target="q_intent"),
            Edge(source="q_intent", target="d_route"),
            Edge(
                source="d_route",
                target="q_support_issue",
                condition_description="Path: technical_support",
                priority=1
            ),
            Edge(
                source="d_route", 
                target="q_product_interest",
                condition_description="Path: product_inquiry", 
                priority=2
            ),
            Edge(source="q_support_issue", target="support_done"),
            Edge(source="q_product_interest", target="sales_done"),
        ],
    )


@pytest.fixture
def escalation_flow():
    """Create a simple flow for testing escalations."""
    return Flow(
        id="escalation_test", 
        metadata=FlowMetadata(name="Escalation Test"),
        entry="start",
        nodes=[
            DecisionNode(id="start"),
            QuestionNode(
                id="q_complex",
                key="complex_request",
                prompt="Por favor, descreva sua necessidade técnica complexa.",
                priority=10,
            ),
            QuestionNode(
                id="q_followup",
                key="followup_info", 
                prompt="Você pode fornecer detalhes adicionais?",
                priority=20,
            ),
            TerminalNode(id="complete", reason="Solicitação concluída"),
        ],
        edges=[
            Edge(source="start", target="q_complex"),
            Edge(source="q_complex", target="q_followup"),
            Edge(source="q_followup", target="complete"),
        ],
    )


class TestSpecificToolIntegration:
    """Tests for specific tool functionality with real LLM calls."""
    
    def test_path_correction_tool(self, real_llm, path_correction_flow):
        """Test that path correction works with real LLM calls."""
        compiler = FlowCompiler()
        compiled = compiler.compile(path_correction_flow)
        runner = FlowTurnRunner(compiled, real_llm, strict_mode=False)
        ctx = runner.initialize_context()
        
        print("\n=== PATH CORRECTION TEST ===")
        
        # 1. Start flow
        result = runner.process_turn(ctx)
        print(f"Initial: {result.assistant_message}")
        rate_limit_delay()
        
        # 2. Express ambiguous intent
        result = runner.process_turn(ctx, "Quero saber sobre seus produtos")
        print(f"Intent captured: {result.answers_diff}")
        rate_limit_delay()
        
        # 3. Get routed (might need to select path)
        result = runner.process_turn(ctx)
        print(f"Routing: {result.assistant_message}")
        
        # If path selection is needed, choose product path
        if "caminho" in result.assistant_message.lower() or "path" in result.assistant_message.lower():
            rate_limit_delay()
            result = runner.process_turn(ctx, "consulta de produto")
            print(f"Path selected: {result.tool_name}")
            rate_limit_delay()
            result = runner.process_turn(ctx)
        
        # 4. Now correct the path - realize we want support instead
        initial_question = result.assistant_message
        rate_limit_delay()
        result = runner.process_turn(ctx, "Na verdade, não quero produtos - preciso de suporte técnico")
        print(f"Correction tool: {result.tool_name}")
        print(f"Correction metadata: {result.ctx.answers}")
        
        # Should trigger PathCorrection or RevisitQuestion
        assert result.tool_name in ["PathCorrection", "RevisitQuestion", "UpdateAnswersFlow"]
        
        # 5. Verify we get routed to correct path
        rate_limit_delay()  
        result = runner.process_turn(ctx)
        corrected_question = result.assistant_message
        
        # Should be different from initial routing
        print(f"Initial question: {initial_question[:50]}...")
        print(f"Corrected question: {corrected_question[:50]}...")
        
        # Should now be asking about technical issues, not products
        assert "técnico" in corrected_question.lower() or "problema" in corrected_question.lower() or "suporte" in corrected_question.lower()
        
        print("✅ Path correction working!")
    
    def test_unknown_answer_tool(self, real_llm, escalation_flow):
        """Test unknown answer handling."""
        compiler = FlowCompiler()
        compiled = compiler.compile(escalation_flow)
        runner = FlowTurnRunner(compiled, real_llm, strict_mode=False)
        ctx = runner.initialize_context()
        
        print("\n=== UNKNOWN ANSWER TEST ===")
        
        # Get to a question
        result = runner.process_turn(ctx)
        print(f"Question: {result.assistant_message}")
        rate_limit_delay()
        
        # Express genuine uncertainty
        result = runner.process_turn(ctx, "Sinceramente não sei como descrever isso - não tenho ideia")
        print(f"Tool chosen: {result.tool_name}")
        print(f"Escalate: {result.escalate}")
        
        # LLM might choose UnknownAnswer, ClarifyQuestion, or intelligently escalate for complex cases
        assert result.tool_name in ["UnknownAnswer", "ClarifyQuestion", "RequestHumanHandoff"]
        
        if result.tool_name == "RequestHumanHandoff":
            print("✅ Intelligent escalation for complex unknown requests!")
        else:
            print("✅ Unknown answer handling working!")
    
    def test_escalation_triggers(self, real_llm, escalation_flow):
        """Test escalation scenarios."""
        compiler = FlowCompiler()
        compiled = compiler.compile(escalation_flow)
        runner = FlowTurnRunner(compiled, real_llm, strict_mode=False)
        ctx = runner.initialize_context()
        
        print("\n=== ESCALATION TEST ===")
        
        # Get to a question
        result = runner.process_turn(ctx)
        print(f"Question: {result.assistant_message}")
        rate_limit_delay()
        
        # Express frustration and request human help
        result = runner.process_turn(ctx, "Isso está muito confuso e estou ficando frustrado. Posso falar com um atendente humano por favor?")
        print(f"Tool chosen: {result.tool_name}")
        print(f"Escalate: {result.escalate}")
        
        # Should escalate
        if result.tool_name == "RequestHumanHandoff":
            assert result.escalate == True
            print("✅ Direct escalation working!")
        else:
            # Try more explicit request
            rate_limit_delay()
            result = runner.process_turn(ctx, "Quero falar com um representante humano imediatamente")
            print(f"Second attempt - Tool: {result.tool_name}, Escalate: {result.escalate}")
            
            assert result.tool_name == "RequestHumanHandoff" or result.escalate == True
            print("✅ Escalation working!")
    
    def test_revisit_question_tool(self, real_llm, path_correction_flow):
        """Test revisiting and changing previous answers."""
        compiler = FlowCompiler()
        compiled = compiler.compile(path_correction_flow)
        runner = FlowTurnRunner(compiled, real_llm, strict_mode=False)
        ctx = runner.initialize_context()
        
        print("\n=== REVISIT QUESTION TEST ===")
        
        # Progress through a few questions
        result = runner.process_turn(ctx)
        rate_limit_delay()
        
        result = runner.process_turn(ctx, "Preciso de informações sobre produtos")
        print(f"Initial answer: {result.answers_diff}")
        rate_limit_delay()
        
        # Progress further
        result = runner.process_turn(ctx)
        if "caminho" in result.assistant_message.lower() or "path" in result.assistant_message.lower():
            rate_limit_delay()
            result = runner.process_turn(ctx, "consulta de produto")
            rate_limit_delay() 
            result = runner.process_turn(ctx)
        
        # Now change mind about earlier answer
        rate_limit_delay()
        result = runner.process_turn(ctx, "Espera, quero mudar minha resposta anterior - na verdade preciso de suporte, não produtos")
        print(f"Revision tool: {result.tool_name}")
        print(f"Updated answers: {result.ctx.answers}")
        
        # Should trigger RevisitQuestion or PathCorrection
        assert result.tool_name in ["RevisitQuestion", "PathCorrection", "UpdateAnswersFlow"]
        
        print("✅ Question revisiting working!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
