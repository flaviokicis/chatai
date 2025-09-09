"""
Comprehensive integration test that uses actual LLM calls to test the entire flow system.

This test exercises all flow tools, decision making, path corrections, and handles
a complete flow conversation from start to finish using real LLM interactions.
"""

import os
import time
from typing import Any

import pytest
from langchain.chat_models import init_chat_model

from app.core.langchain_adapter import LangChainToolsLLM
from app.flow_core.compiler import FlowCompiler
from app.flow_core.ir import (
    DecisionNode,
    Edge,
    Flow,
    FlowMetadata,
    GuardRef,
    QuestionNode,
    TerminalNode,
)
from app.flow_core.runner import FlowTurnRunner


def rate_limit_delay():
    """Add delay to avoid hitting API rate limits."""
    time.sleep(0.5)


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
def comprehensive_flow():
    """
    Create a comprehensive test flow that exercises all features:
    - Multiple paths/branches
    - Decision nodes
    - Required vs optional questions
    - Dependencies
    - Path selection and correction opportunities
    """
    return Flow(
        id="integration_test_flow",
        metadata=FlowMetadata(
            name="Integration Test Flow",
            description="Comprehensive flow for testing all LLM features",
            version="1.0.0",
        ),
        entry="start",
        nodes=[
            DecisionNode(id="start", label="Start"),

            # Initial intent capture
            QuestionNode(
                id="q_intent",
                key="user_intent",
                prompt="Oi! Como posso te ajudar hoje?",
                priority=10,
                required=True,
            ),

            # Decision point for routing
            DecisionNode(
                id="d_route",
                label="Route by Intent",
                decision_type="automatic"
            ),

            # Service request path
            QuestionNode(
                id="q_service_type",
                key="service_type",
                prompt="Que tipo de serviço você está procurando? (consultoria, suporte, ou vendas)",
                allowed_values=["consultoria", "suporte", "vendas"],
                priority=20,
                required=True,
            ),
            QuestionNode(
                id="q_service_urgency",
                key="urgency",
                prompt="Qual é a urgência desta solicitação? (baixa, média, alta)",
                allowed_values=["baixa", "média", "alta"],
                priority=30,
                required=False,  # Optional - can test unknown answers
            ),
            QuestionNode(
                id="q_service_details",
                key="service_details",
                prompt="Por favor, descreva suas necessidades específicas com mais detalhes.",
                priority=40,
                required=True,
                dependencies=["service_type"],
            ),

            # Product inquiry path
            QuestionNode(
                id="q_product_category",
                key="product_category",
                prompt="Qual categoria de produto te interessa? (software, hardware, ou serviços)",
                allowed_values=["software", "hardware", "serviços"],
                priority=20,
                required=True,
            ),
            QuestionNode(
                id="q_budget_range",
                key="budget_range",
                prompt="Qual é sua faixa de orçamento? (até_1k, 1k_a_10k, acima_10k)",
                allowed_values=["até_1k", "1k_a_10k", "acima_10k"],
                priority=30,
                required=False,  # Can test skip/unknown
            ),
            QuestionNode(
                id="q_timeline",
                key="timeline",
                prompt="Quando você está pensando em tomar uma decisão? (esta_semana, este_mês, próximo_trimestre)",
                allowed_values=["esta_semana", "este_mês", "próximo_trimestre"],
                priority=40,
                required=True,
            ),

            # General info path
            QuestionNode(
                id="q_info_topic",
                key="info_topic",
                prompt="Sobre que assunto você gostaria de saber mais?",
                priority=20,
                required=True,
            ),
            QuestionNode(
                id="q_experience_level",
                key="experience_level",
                prompt="Qual é seu nível de experiência com esse assunto? (iniciante, intermediário, avançado)",
                allowed_values=["iniciante", "intermediário", "avançado"],
                priority=30,
                required=False,
            ),

            # Common final questions for all paths
            QuestionNode(
                id="q_contact_method",
                key="contact_method",
                prompt="Como você prefere ser contatado? (email, telefone, ou chat)",
                allowed_values=["email", "telefone", "chat"],
                priority=90,
                required=True,
                skippable=False,  # Force completion
            ),
            QuestionNode(
                id="q_contact_info",
                key="contact_info",
                prompt="Por favor, forneça suas informações de contato.",
                priority=100,
                required=True,
                dependencies=["contact_method"],
            ),

            # Terminal nodes
            TerminalNode(id="service_complete", reason="Solicitação de serviço concluída"),
            TerminalNode(id="product_complete", reason="Consulta de produto concluída"),
            TerminalNode(id="info_complete", reason="Solicitação de informação concluída"),
        ],
        edges=[
            # Start to intent
            Edge(source="start", target="q_intent", priority=1),
            Edge(source="q_intent", target="d_route", priority=1),

            # Route to different paths
            Edge(
                source="d_route",
                target="q_service_type",
                guard=GuardRef(fn="always", args={"if": "user needs service or support"}),
                priority=1,
                condition_description="Path: service_request"
            ),
            Edge(
                source="d_route",
                target="q_product_category",
                guard=GuardRef(fn="always", args={"if": "user asking about products"}),
                priority=2,
                condition_description="Path: product_inquiry"
            ),
            Edge(
                source="d_route",
                target="q_info_topic",
                guard=GuardRef(fn="always", args={"if": "user wants general information"}),
                priority=3,
                condition_description="Path: general_info"
            ),

            # Service request flow
            Edge(source="q_service_type", target="q_service_urgency", priority=1),
            Edge(source="q_service_urgency", target="q_service_details", priority=1),
            Edge(source="q_service_details", target="q_contact_method", priority=1),

            # Product inquiry flow
            Edge(source="q_product_category", target="q_budget_range", priority=1),
            Edge(source="q_budget_range", target="q_timeline", priority=1),
            Edge(source="q_timeline", target="q_contact_method", priority=1),

            # General info flow
            Edge(source="q_info_topic", target="q_experience_level", priority=1),
            Edge(source="q_experience_level", target="q_contact_method", priority=1),

            # Final completion
            Edge(source="q_contact_method", target="q_contact_info", priority=1),

            # Terminal routing (simplified - all lead to same completion for now)
            Edge(
                source="q_contact_info",
                target="service_complete",
                guard=GuardRef(fn="answers_equals", args={"key": "service_type", "value": "consulting"}),
                priority=1
            ),
            Edge(
                source="q_contact_info",
                target="service_complete",
                guard=GuardRef(fn="answers_equals", args={"key": "service_type", "value": "support"}),
                priority=2
            ),
            Edge(
                source="q_contact_info",
                target="service_complete",
                guard=GuardRef(fn="answers_equals", args={"key": "service_type", "value": "sales"}),
                priority=3
            ),
            Edge(
                source="q_contact_info",
                target="product_complete",
                guard=GuardRef(fn="answers_has", args={"key": "product_category"}),
                priority=4
            ),
            Edge(
                source="q_contact_info",
                target="info_complete",
                guard=GuardRef(fn="answers_has", args={"key": "info_topic"}),
                priority=5
            ),
        ],
    )


class TestLLMFlowIntegration:
    """Integration tests using real LLM calls."""

    @pytest.mark.integration
    @pytest.mark.llm
    def test_basic_llm_integration_core_tools(self, real_llm, comprehensive_flow):
        """
        Test basic LLM integration with core tools to verify the system works end-to-end.
        This is a simpler test that focuses on essential functionality with fewer API calls.
        """
        compiler = FlowCompiler()
        compiled = compiler.compile(comprehensive_flow)
        runner = FlowTurnRunner(compiled, real_llm, strict_mode=False)
        ctx = runner.initialize_context()

        # Track key interactions
        interactions = []

        # 1. Initial prompt should work
        result = runner.process_turn(ctx)
        assert result.assistant_message is not None
        assert "ajudar" in result.assistant_message.lower()
        interactions.append(("initial", "", result.assistant_message, result.tool_name))
        rate_limit_delay()

        # 2. LLM should extract intent correctly
        result = runner.process_turn(ctx, "Preciso de suporte técnico")
        assert result.answers_diff.get("user_intent") is not None
        assert result.tool_name == "UpdateAnswers"
        interactions.append(("intent", "Preciso de suporte técnico", result.assistant_message, result.tool_name))
        rate_limit_delay()

        # 3. Should progress to next question
        result = runner.process_turn(ctx)
        assert not result.terminal
        interactions.append(("progress", "", result.assistant_message, result.tool_name))
        rate_limit_delay()

        # 4. Test clarification request
        result = runner.process_turn(ctx, "O que você quer dizer com isso?")
        assert result.tool_name == "ClarifyQuestion"
        interactions.append(("clarify", "O que você quer dizer com isso?", result.assistant_message, result.tool_name))
        rate_limit_delay()

        # 5. Test providing answer after clarification
        result = runner.process_turn(ctx, "suporte")
        # Should extract answer or provide information
        assert result.tool_name in ["UpdateAnswers", "StayOnThisNode"]
        interactions.append(("answer", "suporte", result.assistant_message, result.tool_name))

        # Print interactions for debugging
        print("\n=== BASIC INTEGRATION TEST LOG ===")
        for step, user_input, assistant_msg, tool in interactions:
            print(f"[{step}] User: '{user_input}' -> Tool: {tool}")
            if assistant_msg:
                print(f"    Assistant: {assistant_msg[:100]}...")

        # Verify we have essential functionality working
        assert len([i for i in interactions if i[3] == "UpdateAnswers"]) >= 1, "Should extract answers"
        assert len([i for i in interactions if i[3] == "ClarifyQuestion"]) >= 1, "Should handle clarifications"
        assert len(ctx.answers) > 0, "Should collect some answers"

        print(f"\n✅ Core LLM integration working! Collected answers: {ctx.answers}")

    @pytest.mark.integration
    @pytest.mark.llm
    @pytest.mark.slow
    def test_complete_service_flow_with_all_tools(self, real_llm, comprehensive_flow):
        """
        Test a complete service flow that exercises all tools:
        - Normal flow progression
        - Path corrections
        - Unknown answers
        - Clarification requests  
        - Answer revisions
        - Skip attempts
        - Escalation triggers
        """
        compiler = FlowCompiler()
        compiled = compiler.compile(comprehensive_flow)
        runner = FlowTurnRunner(compiled, real_llm, strict_mode=False)
        ctx = runner.initialize_context()

        # Track conversation for debugging
        conversation_log: list[dict[str, Any]] = []

        def log_turn(user_input: str, result):
            conversation_log.append({
                "user": user_input,
                "assistant": result.assistant_message,
                "tool": result.tool_name,
                "answers": dict(result.ctx.answers),
                "escalate": result.escalate,
                "terminal": result.terminal
            })

        # 1. Initial greeting/prompt
        result = runner.process_turn(ctx)
        assert result.assistant_message is not None
        assert "ajudar" in result.assistant_message.lower()
        assert not result.terminal
        log_turn("", result)

        # 2. Express intent for service
        result = runner.process_turn(ctx, "Preciso de ajuda com suporte técnico para nosso sistema de software")
        assert result.answers_diff.get("user_intent") is not None
        log_turn("Preciso de ajuda com suporte técnico para nosso sistema de software", result)

        # 3. Should route to service path automatically or ask for path selection
        result = runner.process_turn(ctx)
        assert not result.terminal

        # If decision node asks for path selection, provide the service path
        if "caminho" in result.assistant_message.lower() or "path" in result.assistant_message.lower():
            log_turn("", result)
            # Answer the path selection
            result = runner.process_turn(ctx, "solicitação de serviço")
            log_turn("solicitação de serviço", result)
            # Get the next prompt after path selection
            result = runner.process_turn(ctx)

        # Now should be asking about service type
        assert "serviço" in result.assistant_message.lower() or "suporte" in result.assistant_message.lower()
        log_turn("", result)

        # 4. Answer service type
        result = runner.process_turn(ctx, "Preciso de suporte")
        assert result.answers_diff.get("service_type") == "suporte"
        log_turn("Preciso de suporte", result)

        # 5. Test CLARIFICATION REQUEST - ask about urgency question
        result = runner.process_turn(ctx)
        assert "urgên" in result.assistant_message.lower()
        log_turn("", result)

        result = runner.process_turn(ctx, "O que você quer dizer com urgência? Pode explicar os diferentes níveis?")
        assert result.tool_name == "ClarifyQuestion"
        assert not result.terminal
        log_turn("O que você quer dizer com urgência? Pode explicar os diferentes níveis?", result)

        # 6. Test UNKNOWN ANSWER - don't know urgency (LLM might choose ClarifyQuestion or StayOnThisNode)
        result = runner.process_turn(ctx)  # Should still be asking about urgency
        log_turn("", result)

        result = runner.process_turn(ctx, "Não sei o nível de urgência - não tenho ideia")
        # LLM might reasonably choose either ClarifyQuestion or StayOnThisNode for uncertain responses
        assert result.tool_name in ["StayOnThisNode", "ClarifyQuestion"]
        log_turn("Não sei o nível de urgência - não tenho ideia", result)

        # 7. Should continue to service details despite unknown urgency (it's optional)
        result = runner.process_turn(ctx)
        assert "detalh" in result.assistant_message.lower()
        log_turn("", result)

        # 8. Provide service details
        result = runner.process_turn(ctx, "Nossa aplicação principal está travando quando os usuários tentam exportar relatórios grandes. Isso está acontecendo desde a última atualização.")
        assert result.answers_diff.get("service_details") is not None
        log_turn("Nossa aplicação principal está travando quando os usuários tentam exportar relatórios grandes. Isso está acontecendo desde a última atualização.", result)

        # 9. Test ANSWER REVISION - go back and change urgency after providing details
        result = runner.process_turn(ctx)
        log_turn("", result)

        result = runner.process_turn(ctx, "Na verdade, pensando bem, isso é bastante urgente já que está afetando vários usuários")
        assert result.tool_name == "RevisitQuestion"
        assert "urgency" in str(result.ctx.answers)
        log_turn("Na verdade, pensando bem, isso é bastante urgente já que está afetando vários usuários", result)

        # 10. Continue to contact method
        result = runner.process_turn(ctx)
        assert "contato" in result.assistant_message.lower()
        log_turn("", result)

        # 11. Test SKIP ATTEMPT (should not work for required field)
        result = runner.process_turn(ctx, "Prefiro não fornecer informações de contato agora")
        # This might try to skip but should not succeed for required field
        log_turn("Prefiro não fornecer informações de contato agora", result)

        # 12. Eventually provide contact method
        result = runner.process_turn(ctx, "Email está bom")
        assert result.answers_diff.get("contact_method") == "email"
        log_turn("Email está bom", result)

        # 13. Final contact info
        result = runner.process_turn(ctx)
        assert "contato" in result.assistant_message.lower()
        log_turn("", result)

        result = runner.process_turn(ctx, "joao.silva@empresa.com")
        assert result.answers_diff.get("contact_info") is not None
        log_turn("joao.silva@empresa.com", result)

        # 14. Should complete the flow
        result = runner.process_turn(ctx)
        assert result.terminal
        assert "concluí" in result.assistant_message.lower()
        log_turn("", result)

        # Verify we collected all key information
        final_answers = ctx.answers
        assert final_answers.get("user_intent") is not None
        assert final_answers.get("service_type") == "suporte"
        assert final_answers.get("service_details") is not None
        assert final_answers.get("contact_method") == "email"
        assert final_answers.get("contact_info") is not None

        # Print conversation log for debugging
        print("\n=== CONVERSATION LOG ===")
        for i, turn in enumerate(conversation_log):
            print(f"Turn {i+1}:")
            if turn["user"]:
                print(f"  User: {turn['user']}")
            print(f"  Assistant: {turn['assistant']}")
            if turn["tool"]:
                print(f"  Tool: {turn['tool']}")
            print(f"  Answers: {turn['answers']}")
            if turn["escalate"]:
                print("  ⚠️  ESCALATED")
            if turn["terminal"]:
                print("  ✅ TERMINAL")
            print()

    @pytest.mark.integration
    @pytest.mark.llm
    def test_path_correction_flow(self, real_llm, comprehensive_flow):
        """
        Test path correction functionality - user starts on wrong path and corrects it.
        """
        compiler = FlowCompiler()
        compiled = compiler.compile(comprehensive_flow)
        runner = FlowTurnRunner(compiled, real_llm, strict_mode=False)
        ctx = runner.initialize_context()

        # 1. Initial prompt
        result = runner.process_turn(ctx)
        assert not result.terminal

        # 2. Express ambiguous intent that might be misrouted
        result = runner.process_turn(ctx, "I want to learn about your software products")
        assert result.answers_diff.get("user_intent") is not None

        # 3. Should route (possibly to wrong path initially)
        result = runner.process_turn(ctx)
        initial_question = result.assistant_message.lower()

        # 4. Test PATH CORRECTION - user realizes they're on wrong path
        if "category" in initial_question:  # Routed to product path
            result = runner.process_turn(ctx, "Actually, I don't want to buy anything - I just need technical support")
            # Should trigger path correction
            assert result.tool_name in ["PathCorrection", "RevisitQuestion"]
        elif "service" in initial_question:  # Routed to service path
            result = runner.process_turn(ctx, "Sorry, I'm not looking for services - I want to see your products")
            assert result.tool_name in ["PathCorrection", "RevisitQuestion"]

        # Continue the corrected path briefly to verify it worked
        result = runner.process_turn(ctx)
        assert not result.terminal

        # The correction should have led to appropriate questions for the corrected path
        corrected_question = result.assistant_message.lower()
        assert corrected_question != initial_question  # Should be different question

    @pytest.mark.integration
    @pytest.mark.llm
    def test_escalation_triggers(self, real_llm, comprehensive_flow):
        """
        Test various escalation scenarios.
        """
        compiler = FlowCompiler()
        compiled = compiler.compile(comprehensive_flow)
        runner = FlowTurnRunner(compiled, real_llm, strict_mode=False)
        ctx = runner.initialize_context()

        # Get to a question state
        result = runner.process_turn(ctx)
        result = runner.process_turn(ctx, "I have a complex technical issue")
        result = runner.process_turn(ctx)

        # Test escalation due to frustration
        result = runner.process_turn(ctx, "This is getting really confusing and I'm frustrated. Can I speak to a human please?")

        # Should escalate
        if result.tool_name == "RequestHumanHandoff":
            assert result.escalate
        else:
            # Try a more explicit escalation request
            result = runner.process_turn(ctx, "I want to speak to a human agent immediately")
            assert result.tool_name == "RequestHumanHandoff"
            assert result.escalate

    @pytest.mark.integration
    @pytest.mark.llm
    def test_restart_conversation(self, real_llm, comprehensive_flow):
        """
        Test conversation restart functionality.
        """
        compiler = FlowCompiler()
        compiled = compiler.compile(comprehensive_flow)
        runner = FlowTurnRunner(compiled, real_llm, strict_mode=False)
        ctx = runner.initialize_context()

        # Progress through several questions
        result = runner.process_turn(ctx)
        result = runner.process_turn(ctx, "I need product information")
        result = runner.process_turn(ctx)
        result = runner.process_turn(ctx, "software")

        # Should have some answers collected
        assert len(ctx.answers) > 0
        initial_answers_count = len(ctx.answers)

        # Request restart
        result = runner.process_turn(ctx, "Let me start over from scratch please")

        if result.tool_name == "RestartConversation":
            # Context should be reset
            result = runner.process_turn(ctx)
            assert len(ctx.answers) < initial_answers_count  # Should have fewer answers
            assert "accomplish today" in result.assistant_message.lower()  # Back to start

    @pytest.mark.integration
    @pytest.mark.llm
    def test_multiple_path_scenarios(self, real_llm, comprehensive_flow):
        """
        Test different path selections to ensure all routes work.
        """
        compiler = FlowCompiler()
        compiled = compiler.compile(comprehensive_flow)

        # Test product inquiry path
        runner_product = FlowTurnRunner(compiled, real_llm, strict_mode=False)
        ctx_product = runner_product.initialize_context()

        result = runner_product.process_turn(ctx_product)
        result = runner_product.process_turn(ctx_product, "I'm interested in purchasing your software products")
        result = runner_product.process_turn(ctx_product)

        # Should route to product path
        assert "category" in result.assistant_message.lower() or "software" in result.assistant_message.lower()

        # Test info request path
        runner_info = FlowTurnRunner(compiled, real_llm, strict_mode=False)
        ctx_info = runner_info.initialize_context()

        result = runner_info.process_turn(ctx_info)
        result = runner_info.process_turn(ctx_info, "I just want to learn more about what you do")
        result = runner_info.process_turn(ctx_info)

        # Should route to info path
        assert "topic" in result.assistant_message.lower() or "learn" in result.assistant_message.lower()


if __name__ == "__main__":
    # Allow running individual test
    pytest.main([__file__, "-v", "-s"])
