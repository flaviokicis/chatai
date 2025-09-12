"""Test for handling partial answers in flow system.

This test verifies that when a user provides a partial answer to a multi-part question,
the flow correctly stays at the current node instead of advancing prematurely.
"""

import os

import pytest
from langchain.chat_models import init_chat_model

from app.core.langchain_adapter import LangChainToolsLLM
from app.flow_core.compiler import compile_flow
from app.flow_core.ir import Edge, Flow, QuestionNode, TerminalNode
from app.flow_core.runner import FlowTurnRunner
from app.services.tenant_config_service import ProjectContext


@pytest.fixture(scope="module")
def real_llm():
    """Create a real LLM client for integration testing."""
    # Skip if no API key available
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or api_key == "test":
        pytest.skip("GOOGLE_API_KEY not configured - skipping LLM integration tests")

    # Use a fast, cost-effective model for testing
    chat = init_chat_model("gemini-2.0-flash-exp", model_provider="google_genai")
    return LangChainToolsLLM(chat)


@pytest.fixture
def sample_flow_with_multipart_question():
    """Create a flow with a multi-part question similar to the luminarias flow."""
    return Flow(
        id="test_partial_flow",
        entry="q.dimensions",
        nodes=[
            QuestionNode(
                id="q.dimensions",
                key="dimensions_info",
                prompt="Please provide: width, length, number of posts, and height",
            ),
            TerminalNode(
                id="t.complete",
                reason="Thank you, I have all the information I need!",
            ),
        ],
        edges=[
            Edge(
                source="q.dimensions",
                target="t.complete",
                priority=0,
            ),
        ],
    )


def test_partial_answer_stays_at_node(real_llm, sample_flow_with_multipart_question):
    """Test that partial answers don't advance the flow prematurely."""

    # Compile the flow
    compiled_flow = compile_flow(sample_flow_with_multipart_question)

    # Create runner with LLM
    runner = FlowTurnRunner(compiled_flow, real_llm, strict_mode=False)

    # Initialize context
    ctx = runner.initialize_context()

    # Create project context
    project_context = ProjectContext(
        tenant_id="test-tenant",
        project_description="Test project for partial answers",
    )

    # First turn - start the flow
    result1 = runner.process_turn(ctx, "Hello", project_context)

    # Should ask for dimensions
    assert not result1.terminal
    assert ctx.current_node_id == "q.dimensions"
    assert "width" in result1.assistant_message.lower() or "width" in str(result1.messages).lower()

    # Second turn - provide partial answer (missing number of posts)
    result2 = runner.process_turn(ctx, "32 meters by 50 meters, height is 40 meters", project_context)

    # CRITICAL: Should STAY at the same node and ask for missing info
    assert not result2.terminal, "Flow should not be terminal after partial answer"
    assert ctx.current_node_id == "q.dimensions", "Should stay at dimensions node"
    assert not ctx.is_complete, "Context should not be marked complete"

    # Should have saved the partial data
    assert "dimensions_info" in ctx.answers

    # Should ask for the missing information
    assert (
        "post" in result2.assistant_message.lower() or
        "post" in str(result2.messages).lower() or
        "missing" in result2.assistant_message.lower() or
        "missing" in str(result2.messages).lower()
    ), "Should ask for missing posts information"

    # Third turn - provide the missing information
    result3 = runner.process_turn(ctx, "4 posts", project_context)

    # NOW it should complete
    assert result3.terminal or ctx.is_complete, "Flow should be terminal after complete answer"

    # Should have all the data
    assert "dimensions_info" in ctx.answers


def test_short_numerical_response_understood_in_context(real_llm, sample_flow_with_multipart_question):
    """Test that short responses like '4' are understood as answers to pending questions."""

    # Compile the flow
    compiled_flow = compile_flow(sample_flow_with_multipart_question)

    # Create runner with LLM
    runner = FlowTurnRunner(compiled_flow, real_llm, strict_mode=False)

    # Initialize context
    ctx = runner.initialize_context()

    # Create project context
    project_context = ProjectContext(
        tenant_id="test-tenant",
        project_description="Test project for short responses",
    )

    # First turn - start the flow
    result1 = runner.process_turn(ctx, "Hi", project_context)
    assert ctx.current_node_id == "q.dimensions"

    # Second turn - partial answer
    result2 = runner.process_turn(ctx, "width 30m, length 40m, height 35m", project_context)

    # Should stay and ask for posts
    assert not result2.terminal
    assert ctx.current_node_id == "q.dimensions"

    # Third turn - short numerical response
    result3 = runner.process_turn(ctx, "4", project_context)

    # Should understand this as the number of posts and complete
    assert result3.terminal or ctx.is_complete

    # Should NOT treat "4" as a greeting or reset the conversation
    assert "dimensions_info" in ctx.answers


def test_abbreviation_response_understood(real_llm, sample_flow_with_multipart_question):
    """Test that abbreviated responses like '4 tb' (4 também) are understood."""

    # Compile the flow
    compiled_flow = compile_flow(sample_flow_with_multipart_question)

    # Create runner with LLM
    runner = FlowTurnRunner(compiled_flow, real_llm, strict_mode=False)

    # Initialize context
    ctx = runner.initialize_context()

    # Create project context
    project_context = ProjectContext(
        tenant_id="test-tenant",
        project_description="Test project for abbreviations",
    )

    # First turn
    result1 = runner.process_turn(ctx, "Oi", project_context)
    assert ctx.current_node_id == "q.dimensions"

    # Second turn - partial answer in Portuguese
    result2 = runner.process_turn(
        ctx,
        "largura 30m, comprimento 40m, altura 35m",
        project_context
    )

    # Should stay and ask for posts
    assert not result2.terminal
    assert ctx.current_node_id == "q.dimensions"

    # Third turn - abbreviated response "4 tb" meaning "4 também" (4 as well)
    result3 = runner.process_turn(ctx, "4 tb", project_context)

    # Should understand this as the number (4) and complete or continue appropriately
    # Should NOT treat it as a greeting or unclear message
    assert "dimensions_info" in ctx.answers
    assert not any(
        word in str(result3.messages).lower()
        for word in ["olá", "oi", "tudo bem", "como posso"]
    ), "Should not greet the user again"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
