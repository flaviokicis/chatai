"""Comprehensive tests for the enhanced flow_core v2 system."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.llm import LLMClient
from app.flow_core.compiler import FlowCompiler
from app.flow_core.engine import LLMFlowEngine
from app.flow_core.ir import (
    DecisionNode,
    Edge,
    Flow,
    FlowMetadata,
    GuardRef,
    PolicyConversation,
    PolicyValidation,
    QuestionNode,
    TerminalNode,
    ValidationRule,
)
from app.flow_core.llm_responder import LLMFlowResponder
from app.flow_core.state import FlowContext, NodeStatus


class MockLLM(LLMClient):
    """Mock LLM for testing."""

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.responses = responses or []
        self.call_count = 0
        self.last_prompt = None
        self.last_tools = None

    def extract(self, prompt: str, tools: list[type]) -> dict[str, Any]:  # type: ignore[override]
        self.last_prompt = prompt
        self.last_tools = tools

        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response

        # Default response
        return {
            "__tool_name__": "UpdateAnswersFlow",
            "updates": {},
            "assistant_message": "I understand.",
        }


@pytest.fixture
def simple_flow() -> Flow:
    """Create a simple test flow."""
    return Flow(
        id="test_flow",
        metadata=FlowMetadata(
            name="Test Flow",
            description="A simple test flow",
            version="1.0.0",
        ),
        entry="start",
        nodes=[
            DecisionNode(id="start", label="Start"),
            QuestionNode(
                id="q_name",
                key="name",
                prompt="What is your name?",
                priority=10,
                required=True,
            ),
            QuestionNode(
                id="q_age",
                key="age",
                prompt="How old are you?",
                priority=20,
                data_type="number",
                validator="age_validator",
            ),
            QuestionNode(
                id="q_email",
                key="email",
                prompt="What is your email?",
                priority=30,
                data_type="email",
                dependencies=["name"],
            ),
            TerminalNode(id="end", reason="Flow completed successfully"),
        ],
        edges=[
            Edge(source="start", target="q_name", priority=1),
            Edge(source="q_name", target="q_age", priority=1),
            Edge(source="q_age", target="q_email", priority=1),
            Edge(source="q_email", target="end", priority=1),
        ],
        validations={
            "age_validator": ValidationRule(
                type="range",
                min_value=0,
                max_value=150,
                error_message="Age must be between 0 and 150",
            ),
        },
    )


@pytest.fixture
def branching_flow() -> Flow:
    """Create a flow with branching logic."""
    return Flow(
        id="branching_flow",
        metadata=FlowMetadata(name="Branching Flow"),
        entry="start",
        nodes=[
            DecisionNode(id="start"),
            QuestionNode(
                id="q_type",
                key="user_type",
                prompt="Are you a new or existing customer?",
                allowed_values=["new", "existing"],
                priority=10,
            ),
            DecisionNode(id="type_router", decision_type="automatic"),
            QuestionNode(
                id="q_signup",
                key="signup_reason",
                prompt="What brings you here today?",
                priority=20,
            ),
            QuestionNode(
                id="q_account",
                key="account_number",
                prompt="What is your account number?",
                priority=20,
            ),
            TerminalNode(id="new_complete", reason="New customer flow complete"),
            TerminalNode(id="existing_complete", reason="Existing customer flow complete"),
        ],
        edges=[
            Edge(source="start", target="q_type"),
            Edge(source="q_type", target="type_router"),
            Edge(
                source="type_router",
                target="q_signup",
                guard=GuardRef(fn="answers_equals", args={"key": "user_type", "value": "new"}),
                priority=1,
            ),
            Edge(
                source="type_router",
                target="q_account",
                guard=GuardRef(fn="answers_equals", args={"key": "user_type", "value": "existing"}),
                priority=2,
            ),
            Edge(source="q_signup", target="new_complete"),
            Edge(source="q_account", target="existing_complete"),
        ],
    )


@pytest.fixture
def flow_with_policies() -> Flow:
    """Create a flow with custom policies."""
    return Flow(
        id="policy_flow",
        entry="start",
        nodes=[
            DecisionNode(id="start"),
            QuestionNode(
                id="q1",
                key="question1",
                prompt="First question",
                skippable=True,
                revisitable=True,
            ),
            QuestionNode(
                id="q2",
                key="question2",
                prompt="Second question",
                skippable=False,
                max_attempts=2,
            ),
            TerminalNode(id="end"),
        ],
        edges=[
            Edge(source="start", target="q1"),
            Edge(source="q1", target="q2"),
            Edge(source="q2", target="end"),
        ],
        policies={
            "conversation": PolicyConversation(
                allow_clarifications=True,
                max_clarifications=2,
                allow_skip=True,
                allow_revisit=True,
                conversation_style="casual",
            ),
            "validation": PolicyValidation(
                strict_validation=False,
                max_validation_attempts=2,
            ),
        },
    )


class TestFlowCompiler:
    """Tests for the enhanced flow compiler."""

    def test_compile_simple_flow(self, simple_flow: Flow) -> None:
        """Test compiling a simple flow."""
        compiler = FlowCompiler()
        compiled = compiler.compile(simple_flow)

        assert compiled.id == "test_flow"
        assert compiled.entry == "start"
        assert len(compiled.nodes) == 5
        assert len(compiled.question_nodes) == 3
        assert len(compiled.terminal_nodes) == 1
        assert not compiled.has_cycles
        assert not compiled.has_unreachable_nodes

    def test_compile_branching_flow(self, branching_flow: Flow) -> None:
        """Test compiling a flow with branches."""
        compiler = FlowCompiler()
        compiled = compiler.compile(branching_flow)

        assert len(compiled.decision_nodes) == 2
        assert len(compiled.terminal_nodes) == 2

        # Check edge compilation
        type_router_edges = compiled.edges_from.get("type_router", [])
        assert len(type_router_edges) == 2
        assert type_router_edges[0].guard_fn is not None

    def test_validation_detection(self) -> None:
        """Test that compiler detects validation issues."""
        # Flow with unreachable node
        flow = Flow(
            id="broken_flow",
            entry="start",
            nodes=[
                DecisionNode(id="start"),
                QuestionNode(id="q1", key="q1", prompt="Q1"),
                QuestionNode(id="unreachable", key="q2", prompt="Q2"),  # No edge to this
                TerminalNode(id="end"),
            ],
            edges=[
                Edge(source="start", target="q1"),
                Edge(source="q1", target="end"),
            ],
        )

        compiler = FlowCompiler()
        compiled = compiler.compile(flow)

        assert compiled.has_unreachable_nodes
        assert "unreachable" in compiled.validation_warnings[0]

    def test_cycle_detection(self) -> None:
        """Test that compiler detects cycles."""
        flow = Flow(
            id="cyclic_flow",
            entry="n1",
            nodes=[
                DecisionNode(id="n1"),
                DecisionNode(id="n2"),
                DecisionNode(id="n3"),
            ],
            edges=[
                Edge(source="n1", target="n2"),
                Edge(source="n2", target="n3"),
                Edge(source="n3", target="n1"),  # Creates cycle
            ],
        )

        compiler = FlowCompiler()
        compiled = compiler.compile(flow)

        assert compiled.has_cycles
        assert any("Cycle detected" in w for w in compiled.validation_warnings)


class TestFlowContext:
    """Tests for flow context management."""

    def test_context_initialization(self) -> None:
        """Test creating a new flow context."""
        ctx = FlowContext(flow_id="test")

        assert ctx.flow_id == "test"
        assert ctx.current_node_id is None
        assert ctx.answers == {}
        assert ctx.turn_count == 0
        assert not ctx.is_complete

    def test_add_turn(self) -> None:
        """Test adding conversation turns."""
        ctx = FlowContext(flow_id="test")

        ctx.add_turn("user", "Hello", node_id="start")
        ctx.add_turn("assistant", "Hi there!", node_id="start")

        assert ctx.turn_count == 2
        assert len(ctx.history) == 2
        assert ctx.history[0].role == "user"
        assert ctx.history[0].content == "Hello"

    def test_node_state_tracking(self) -> None:
        """Test node state management."""
        ctx = FlowContext(flow_id="test")

        ctx.mark_node_visited("q1", NodeStatus.IN_PROGRESS)
        state = ctx.get_node_state("q1")

        assert state.status == NodeStatus.IN_PROGRESS
        assert state.visits == 1
        assert state.last_visited is not None

        # Visit again
        ctx.mark_node_visited("q1", NodeStatus.COMPLETED)
        assert state.visits == 2
        assert state.status == NodeStatus.COMPLETED

    def test_serialization(self) -> None:
        """Test context serialization and deserialization."""
        ctx = FlowContext(flow_id="test")
        ctx.answers = {"name": "Alice", "age": 30}
        ctx.add_turn("user", "My name is Alice")
        ctx.mark_node_visited("q_name", NodeStatus.COMPLETED)

        # Serialize
        data = ctx.to_dict()
        assert data["flow_id"] == "test"
        assert data["answers"] == {"name": "Alice", "age": 30}
        assert len(data["history"]) == 1

        # Deserialize
        ctx2 = FlowContext.from_dict(data)
        assert ctx2.flow_id == "test"
        assert ctx2.answers == {"name": "Alice", "age": 30}
        assert len(ctx2.history) == 1
        assert ctx2.history[0].content == "My name is Alice"


class TestLLMFlowEngine:
    """Tests for the LLM-oriented flow engine."""

    def test_engine_initialization(self, simple_flow: Flow) -> None:
        """Test engine initialization."""
        compiler = FlowCompiler()
        compiled = compiler.compile(simple_flow)

        engine = LLMFlowEngine(compiled, strict_mode=True)
        ctx = engine.initialize_context()

        assert ctx.flow_id == "test_flow"
        assert ctx.current_node_id == "start"

    def test_strict_mode_processing(self, simple_flow: Flow) -> None:
        """Test engine in strict mode (traditional state machine)."""
        compiler = FlowCompiler()
        compiled = compiler.compile(simple_flow)

        engine = LLMFlowEngine(compiled, strict_mode=True)
        ctx = engine.initialize_context()

        # Process first step
        response = engine.process(ctx)
        assert response.kind == "prompt"
        assert "What is your name?" in response.message

        # Provide answer
        response = engine.process(ctx, "John", {"answer": "John"})
        assert response.kind == "prompt"
        assert "How old are you?" in response.message
        assert ctx.answers["name"] == "John"

    def test_llm_mode_processing(self, simple_flow: Flow) -> None:
        """Test engine in LLM mode (flexible)."""
        mock_llm = MockLLM()
        compiler = FlowCompiler()
        compiled = compiler.compile(simple_flow)

        engine = LLMFlowEngine(compiled, mock_llm, strict_mode=False)
        ctx = engine.initialize_context()

        # Process with LLM assistance
        response = engine.process(ctx, "My name is John")
        assert response.kind == "prompt"

        # LLM should help with navigation
        ctx.answers["name"] = "John"
        response = engine.process(ctx)
        assert response.node_id is not None

    def test_clarification_handling(self, simple_flow: Flow) -> None:
        """Test handling clarification requests."""
        compiler = FlowCompiler()
        compiled = compiler.compile(simple_flow)

        engine = LLMFlowEngine(compiled, strict_mode=False)
        ctx = engine.initialize_context()

        # Move to name question
        engine.process(ctx)

        # Ask for clarification
        response = engine.process(ctx, "What do you mean by name?")
        assert response.kind == "prompt"
        assert ctx.clarification_count > 0

    def test_branching_flow_execution(self, branching_flow: Flow) -> None:
        """Test executing a branching flow."""
        compiler = FlowCompiler()
        compiled = compiler.compile(branching_flow)

        engine = LLMFlowEngine(compiled, strict_mode=True)
        ctx = engine.initialize_context()

        # Get to user type question
        response = engine.process(ctx)
        assert "new or existing" in response.message

        # Answer "new"
        response = engine.process(ctx, "new", {"answer": "new"})

        # Should route to signup question
        assert "brings you here" in response.message

        # Complete new path
        response = engine.process(ctx, "Just browsing", {"answer": "Just browsing"})
        assert response.kind == "terminal"
        assert "New customer" in response.message


class TestLLMFlowResponder:
    """Tests for the LLM flow responder."""

    def test_responder_with_updates(self) -> None:
        """Test responder extracting updates."""
        mock_llm = MockLLM(
            [
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"name": "Alice"},
                    "assistant_message": "Nice to meet you, Alice!",
                    "validated": True,
                }
            ]
        )

        responder = LLMFlowResponder(mock_llm)
        ctx = FlowContext(flow_id="test")

        response = responder.respond(
            "What is your name?",
            "name",
            ctx,
            "I'm Alice",
        )

        assert response.updates == {"name": "Alice"}
        assert response.message == "Nice to meet you, Alice!"
        assert response.tool_name == "UpdateAnswersFlow"

    def test_responder_clarification(self) -> None:
        """Test responder handling clarification."""
        mock_llm = MockLLM(
            [
                {
                    "__tool_name__": "ClarifyQuestion",
                    "assistant_message": "I need your full legal name for the form.",
                    "clarification_type": "format",
                }
            ]
        )

        responder = LLMFlowResponder(mock_llm)
        ctx = FlowContext(flow_id="test")

        response = responder.respond(
            "What is your name?",
            "name",
            ctx,
            "Which name do you want?",
        )

        assert response.updates == {}
        assert "legal name" in response.message
        assert response.tool_name == "ClarifyQuestion"

    def test_responder_escalation(self) -> None:
        """Test responder escalating to human."""
        mock_llm = MockLLM(
            [
                {
                    "__tool_name__": "RequestHumanHandoff",
                    "assistant_message": "Let me connect you with a specialist.",
                    "reason": "complex_request",
                    "context": {"issue": "technical"},
                    "urgency": "high",
                }
            ]
        )

        responder = LLMFlowResponder(mock_llm)
        ctx = FlowContext(flow_id="test")

        response = responder.respond(
            "What is your account number?",
            "account",
            ctx,
            "I have a complex issue with multiple accounts",
        )

        assert response.escalate
        assert response.escalate_reason == "complex_request"
        assert "specialist" in response.message

    def test_responder_with_allowed_values(self) -> None:
        """Test responder with constrained values."""
        mock_llm = MockLLM(
            [
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"color": "blue"},
                    "assistant_message": "Great choice!",
                }
            ]
        )

        responder = LLMFlowResponder(mock_llm)
        ctx = FlowContext(flow_id="test")

        response = responder.respond(
            "What color do you prefer?",
            "color",
            ctx,
            "I like blue",
            allowed_values=["red", "green", "blue"],
        )

        assert response.updates == {"color": "blue"}
        # Check that allowed values were passed in instruction
        assert "red, green, blue" in mock_llm.last_prompt

    def test_pattern_detection(self) -> None:
        """Test conversation pattern detection."""
        mock_llm = MockLLM()
        responder = LLMFlowResponder(mock_llm)
        ctx = FlowContext(flow_id="test")
        ctx.clarification_count = 2

        # Test frustration detection
        response = responder.respond(
            "What is your name?",
            "name",
            ctx,
            "This is so confusing and annoying!",
        )

        assert "frustrated" in mock_llm.last_prompt
        assert "needing clarification" in mock_llm.last_prompt


class TestEndToEndFlows:
    """End-to-end tests of complete flows."""

    def test_complete_simple_flow(self, simple_flow: Flow) -> None:
        """Test completing a simple flow end-to-end."""
        # Set up
        compiler = FlowCompiler()
        compiled = compiler.compile(simple_flow)

        mock_llm = MockLLM(
            [
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"name": "Bob"},
                    "assistant_message": "Nice to meet you, Bob!",
                },
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"age": "25"},
                    "assistant_message": "Got it, you're 25.",
                },
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"email": "bob@example.com"},
                    "assistant_message": "Thanks for your email!",
                },
            ]
        )

        engine = LLMFlowEngine(compiled, mock_llm, strict_mode=True)
        responder = LLMFlowResponder(mock_llm)
        ctx = engine.initialize_context()

        # Flow execution
        messages = [
            "Bob",
            "25",
            "bob@example.com",
        ]

        for msg in messages:
            response = engine.process(ctx)
            if response.kind == "terminal":
                break

            # Simulate responder interaction
            resp = responder.respond(
                response.message or "",
                ctx.pending_field,
                ctx,
                msg,
            )

            # Apply updates
            if resp.updates and ctx.pending_field in resp.updates:
                engine.process(ctx, msg, {"answer": resp.updates[ctx.pending_field]})

        # Verify completion
        assert ctx.answers == {
            "name": "Bob",
            "age": "25",
            "email": "bob@example.com",
        }

        # Final step should be terminal
        response = engine.process(ctx)
        assert response.kind == "terminal"

    def test_flow_with_clarifications_and_skips(self, flow_with_policies: Flow) -> None:
        """Test a flow with clarifications and skips."""
        compiler = FlowCompiler()
        compiled = compiler.compile(flow_with_policies)

        mock_llm = MockLLM(
            [
                {
                    "__tool_name__": "ClarifyQuestion",
                    "assistant_message": "This question helps us understand your preferences.",
                    "clarification_type": "purpose",
                },
                {
                    "__tool_name__": "SkipQuestion",
                    "assistant_message": "No problem, let's skip this one.",
                    "reason": "prefer_not_to_answer",
                },
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"question2": "answer2"},
                    "assistant_message": "Thanks for that answer!",
                },
            ]
        )

        engine = LLMFlowEngine(compiled, mock_llm, strict_mode=False)
        ctx = engine.initialize_context()

        # Start flow
        response = engine.process(ctx)
        assert response.kind == "prompt"

        # Ask for clarification using the responder pattern
        from app.flow_core.llm_responder import LLMFlowResponder

        responder = LLMFlowResponder(mock_llm)

        # Process user clarification request
        llm_response = responder.respond(
            response.message or "", ctx.pending_field, ctx, "Why do you need this?"
        )

        # The LLM should return a clarification
        assert llm_response.tool_name == "ClarifyQuestion"
        assert "understand your preferences" in llm_response.message

        # Skip the question using responder pattern
        skip_response = responder.respond(
            response.message or "", ctx.pending_field, ctx, "I'd rather not say"
        )

        # The LLM should return a skip
        assert skip_response.tool_name == "SkipQuestion"
        assert "No problem" in skip_response.message

        # Continue to next question using responder pattern
        final_response = responder.respond(
            response.message or "", ctx.pending_field, ctx, "Here's my answer to question 2"
        )

        # The LLM should extract the answer
        assert final_response.tool_name == "UpdateAnswersFlow"
        assert "Thanks for that answer!" in final_response.message

        # Apply the updates to context (like the agent does)
        for k, v in final_response.updates.items():
            ctx.answers[k] = v

        # Process with engine to advance the flow
        if final_response.updates and ctx.pending_field in final_response.updates:
            engine.process(ctx, None, {"answer": final_response.updates[ctx.pending_field]})

        assert "question2" in ctx.answers or ctx.is_complete


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
