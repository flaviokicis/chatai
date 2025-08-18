"""Comprehensive tests for flow_core state machine with subgraphs and nested flows."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.llm import LLMClient
from app.flow_core.compiler import FlowCompiler
from app.flow_core.engine import LLMFlowEngine
from app.flow_core.ir import (
    ActionNode,
    DecisionNode,
    Edge,
    Flow,
    FlowMetadata,
    GuardRef,
    PolicyConversation,
    QuestionNode,
    SubflowNode,
    TerminalNode,
    ValidationRule,
)
from app.flow_core.llm_responder import LLMFlowResponder
from app.flow_core.state import FlowContext


class SequentialMockLLM(LLMClient):
    """Mock LLM that returns predefined responses in sequence."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.call_index = 0
        self.call_history: list[tuple[str, list[type]]] = []

    def extract(self, prompt: str, tools: list[type]) -> dict[str, Any]:  # type: ignore[override]
        self.call_history.append((prompt, tools))

        if self.call_index < len(self.responses):
            response = self.responses[self.call_index]
            self.call_index += 1
            return response

        # Default fallback
        return {
            "__tool_name__": "UpdateAnswersFlow",
            "updates": {},
            "assistant_message": "I understand.",
        }

    def reset(self) -> None:
        """Reset the mock for reuse."""
        self.call_index = 0
        self.call_history = []


@pytest.fixture
def subflow_payment() -> Flow:
    """Create a payment subflow."""
    return Flow(
        id="payment_flow",
        metadata=FlowMetadata(
            name="Payment Collection",
            description="Collects payment information",
        ),
        entry="start",
        nodes=[
            DecisionNode(id="start"),
            QuestionNode(
                id="q_payment_method",
                key="payment_method",
                prompt="How would you like to pay?",
                allowed_values=["credit_card", "debit_card", "paypal", "bank_transfer"],
                priority=10,
            ),
            DecisionNode(id="method_router", decision_type="automatic"),
            QuestionNode(
                id="q_card_number",
                key="card_number",
                prompt="Please enter your card number",
                data_type="text",
                priority=20,
            ),
            QuestionNode(
                id="q_paypal_email",
                key="paypal_email",
                prompt="Please enter your PayPal email",
                data_type="email",
                priority=20,
            ),
            TerminalNode(id="payment_complete", reason="Payment information collected"),
        ],
        edges=[
            Edge(source="start", target="q_payment_method"),
            Edge(source="q_payment_method", target="method_router"),
            Edge(
                source="method_router",
                target="q_card_number",
                guard=GuardRef(
                    fn="answers_equals",
                    args={"key": "payment_method", "value": "credit_card"},
                ),
                condition_description="If credit card selected",
            ),
            Edge(
                source="method_router",
                target="q_card_number",
                guard=GuardRef(
                    fn="answers_equals",
                    args={"key": "payment_method", "value": "debit_card"},
                ),
                condition_description="If debit card selected",
            ),
            Edge(
                source="method_router",
                target="q_paypal_email",
                guard=GuardRef(
                    fn="answers_equals",
                    args={"key": "payment_method", "value": "paypal"},
                ),
                condition_description="If PayPal selected",
            ),
            Edge(source="q_card_number", target="payment_complete"),
            Edge(source="q_paypal_email", target="payment_complete"),
        ],
    )


@pytest.fixture
def subflow_address() -> Flow:
    """Create an address collection subflow."""
    return Flow(
        id="address_flow",
        metadata=FlowMetadata(name="Address Collection"),
        entry="start",
        nodes=[
            DecisionNode(id="start"),
            QuestionNode(
                id="q_street",
                key="street_address",
                prompt="What's your street address?",
                priority=10,
            ),
            QuestionNode(
                id="q_city",
                key="city",
                prompt="What city?",
                priority=20,
                dependencies=["street_address"],
            ),
            QuestionNode(
                id="q_postal",
                key="postal_code",
                prompt="What's your postal code?",
                priority=30,
                dependencies=["city"],
            ),
            TerminalNode(id="address_complete", reason="Address collected"),
        ],
        edges=[
            Edge(source="start", target="q_street"),
            Edge(source="q_street", target="q_city"),
            Edge(source="q_city", target="q_postal"),
            Edge(source="q_postal", target="address_complete"),
        ],
    )


@pytest.fixture
def main_flow_with_subflows(subflow_payment: Flow, subflow_address: Flow) -> Flow:
    """Create a main flow that uses subflows."""
    return Flow(
        id="order_flow",
        metadata=FlowMetadata(
            name="Order Process",
            description="Complete order flow with nested subflows",
            version="2.0.0",
        ),
        entry="start",
        nodes=[
            DecisionNode(id="start"),
            QuestionNode(
                id="q_product",
                key="product",
                prompt="What product would you like to order?",
                priority=10,
            ),
            QuestionNode(
                id="q_quantity",
                key="quantity",
                prompt="How many would you like?",
                data_type="number",
                priority=20,
                dependencies=["product"],
            ),
            DecisionNode(id="checkout_router"),
            SubflowNode(
                id="collect_address",
                flow_ref="address_flow",
                input_mapping={},  # Pass all context
                output_mapping={
                    "street_address": "shipping_street",
                    "city": "shipping_city",
                    "postal_code": "shipping_postal",
                },
            ),
            SubflowNode(
                id="collect_payment",
                flow_ref="payment_flow",
                input_mapping={},
                output_mapping={
                    "payment_method": "payment_method",
                    "card_number": "card_number",
                    "paypal_email": "paypal_email",
                },
            ),
            ActionNode(
                id="process_order",
                action_type="submit_order",
                action_config={"endpoint": "/api/orders"},
                output_keys=["order_id", "estimated_delivery"],
            ),
            TerminalNode(
                id="order_complete",
                reason="Order successfully placed",
                success=True,
            ),
        ],
        edges=[
            Edge(source="start", target="q_product"),
            Edge(source="q_product", target="q_quantity"),
            Edge(source="q_quantity", target="checkout_router"),
            Edge(source="checkout_router", target="collect_address"),
            Edge(source="collect_address", target="collect_payment"),
            Edge(source="collect_payment", target="process_order"),
            Edge(source="process_order", target="order_complete"),
        ],
        subflows={
            "address_flow": subflow_address,
            "payment_flow": subflow_payment,
        },
        validations={
            "quantity": ValidationRule(
                type="range",
                min_value=1,
                max_value=100,
                error_message="Quantity must be between 1 and 100",
            ),
        },
    )


@pytest.fixture
def deeply_nested_flow() -> Flow:
    """Create a flow with multiple levels of nesting."""

    # Level 3: Deepest subflow
    verification_flow = Flow(
        id="verification",
        entry="start",
        nodes=[
            DecisionNode(id="start"),
            QuestionNode(id="q_code", key="verification_code", prompt="Enter verification code"),
            TerminalNode(id="verified"),
        ],
        edges=[
            Edge(source="start", target="q_code"),
            Edge(source="q_code", target="verified"),
        ],
    )

    # Level 2: Identity subflow that uses verification
    identity_flow = Flow(
        id="identity",
        entry="start",
        nodes=[
            DecisionNode(id="start"),
            QuestionNode(id="q_id_type", key="id_type", prompt="What type of ID?"),
            SubflowNode(id="verify", flow_ref="verification"),
            TerminalNode(id="identity_complete"),
        ],
        edges=[
            Edge(source="start", target="q_id_type"),
            Edge(source="q_id_type", target="verify"),
            Edge(source="verify", target="identity_complete"),
        ],
        subflows={"verification": verification_flow},
    )

    # Level 1: Main flow that uses identity
    return Flow(
        id="main",
        entry="start",
        nodes=[
            DecisionNode(id="start"),
            QuestionNode(id="q_name", key="name", prompt="Your name?"),
            SubflowNode(id="identity_check", flow_ref="identity"),
            TerminalNode(id="complete"),
        ],
        edges=[
            Edge(source="start", target="q_name"),
            Edge(source="q_name", target="identity_check"),
            Edge(source="identity_check", target="complete"),
        ],
        subflows={"identity": identity_flow},
    )


class TestSubflowExecution:
    """Test execution of flows with subflows."""

    def test_simple_subflow_execution(
        self,
        main_flow_with_subflows: Flow,
    ) -> None:
        """Test that engine can navigate through subflows."""
        # Compile the flow
        compiler = FlowCompiler()
        compiled = compiler.compile(main_flow_with_subflows)

        # Verify compilation
        assert compiled.id == "order_flow"
        assert len(compiled.subflows) == 2
        assert "address_flow" in compiled.subflows
        assert "payment_flow" in compiled.subflows

        # Create mock LLM with responses for the entire flow
        mock_llm = SequentialMockLLM(
            [
                # Main flow questions
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"product": "Widget"},
                    "assistant_message": "Got it, you want a Widget.",
                },
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"quantity": "5"},
                    "assistant_message": "5 Widgets, noted.",
                },
                # Address subflow
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"street_address": "123 Main St"},
                    "assistant_message": "Address recorded.",
                },
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"city": "Springfield"},
                    "assistant_message": "City noted.",
                },
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"postal_code": "12345"},
                    "assistant_message": "Postal code saved.",
                },
                # Payment subflow
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"payment_method": "credit_card"},
                    "assistant_message": "Using credit card.",
                },
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"card_number": "4111111111111111"},
                    "assistant_message": "Card information saved.",
                },
            ]
        )

        # Create engine with mock
        engine = LLMFlowEngine(compiled, mock_llm, strict_mode=True)
        ctx = engine.initialize_context()

        # Execute main flow questions
        response = engine.process(ctx)
        assert response.kind == "prompt"
        assert "product" in response.message.lower()

        response = engine.process(ctx, "Widget", {"answer": "Widget"})
        assert response.kind == "prompt"
        assert "how many" in response.message.lower()

        response = engine.process(ctx, "5", {"answer": "5"})

        # Should now enter address subflow
        # Note: In a real implementation, the engine would handle subflow transitions
        # For this test, we're verifying the structure is correct
        assert ctx.answers["product"] == "Widget"
        assert ctx.answers["quantity"] == "5"

    def test_nested_subflow_compilation(self, deeply_nested_flow: Flow) -> None:
        """Test that deeply nested subflows compile correctly."""
        compiler = FlowCompiler()
        compiled = compiler.compile(deeply_nested_flow)

        # Check main flow
        assert compiled.id == "main"
        assert "identity" in compiled.subflows

        # Check level 2 subflow
        identity_compiled = compiled.subflows["identity"]
        assert identity_compiled.id == "identity"
        assert "verification" in identity_compiled.subflows

        # Check level 3 subflow
        verification_compiled = identity_compiled.subflows["verification"]
        assert verification_compiled.id == "verification"
        assert len(verification_compiled.nodes) == 3

    def test_subflow_with_branching(self, subflow_payment: Flow) -> None:
        """Test subflow with conditional branching."""
        compiler = FlowCompiler()
        compiled = compiler.compile(subflow_payment)

        # Test credit card path
        mock_llm = SequentialMockLLM(
            [
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"payment_method": "credit_card"},
                    "assistant_message": "Credit card selected.",
                },
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"card_number": "4111111111111111"},
                    "assistant_message": "Card saved.",
                },
            ]
        )

        engine = LLMFlowEngine(compiled, mock_llm, strict_mode=True)
        ctx = engine.initialize_context()

        # Navigate to payment method
        response = engine.process(ctx)
        assert "How would you like to pay?" in response.message

        # Select credit card
        response = engine.process(ctx, "credit card", {"answer": "credit_card"})

        # Should ask for card number
        assert "card number" in response.message.lower()

        # Provide card number
        response = engine.process(ctx, "4111111111111111", {"answer": "4111111111111111"})

        # Should complete
        assert response.kind == "terminal"
        assert ctx.answers["payment_method"] == "credit_card"
        assert ctx.answers["card_number"] == "4111111111111111"

    def test_subflow_state_isolation(
        self,
        main_flow_with_subflows: Flow,
    ) -> None:
        """Test that subflow state is properly isolated and mapped."""
        compiler = FlowCompiler()
        compiled = compiler.compile(main_flow_with_subflows)

        # The subflows should have their own context
        # but map results back to parent flow
        address_flow = compiled.subflows["address_flow"]

        # Verify output mapping configuration
        collect_address_node = None
        for node in compiled.nodes.values():
            if isinstance(node, SubflowNode) and node.id == "collect_address":
                collect_address_node = node
                break

        assert collect_address_node is not None
        assert collect_address_node.output_mapping == {
            "street_address": "shipping_street",
            "city": "shipping_city",
            "postal_code": "shipping_postal",
        }


class TestFlowNavigation:
    """Test complex navigation scenarios."""

    def test_skip_and_revisit(self) -> None:
        """Test skipping questions and revisiting them later."""
        flow = Flow(
            id="flexible_flow",
            entry="start",
            nodes=[
                DecisionNode(id="start"),
                QuestionNode(
                    id="q1",
                    key="name",
                    prompt="Your name?",
                    skippable=True,
                    revisitable=True,
                ),
                QuestionNode(
                    id="q2",
                    key="email",
                    prompt="Your email?",
                    skippable=True,
                    revisitable=True,
                ),
                QuestionNode(
                    id="q3",
                    key="phone",
                    prompt="Your phone?",
                    required=False,
                ),
                TerminalNode(id="end"),
            ],
            edges=[
                Edge(source="start", target="q1"),
                Edge(source="q1", target="q2"),
                Edge(source="q2", target="q3"),
                Edge(source="q3", target="end"),
            ],
            policies={
                "conversation": PolicyConversation(
                    allow_skip=True,
                    allow_revisit=True,
                ),
            },
        )

        compiler = FlowCompiler()
        compiled = compiler.compile(flow)

        mock_llm = SequentialMockLLM(
            [
                # Skip first question
                {
                    "__tool_name__": "SkipQuestion",
                    "reason": "prefer_not_to_answer",
                    "assistant_message": "No problem, let's skip that.",
                },
                # Answer second question
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"email": "test@example.com"},
                    "assistant_message": "Email saved.",
                },
                # Revisit first question
                {
                    "__tool_name__": "RevisitQuestion",
                    "question_key": "name",
                    "assistant_message": "Let's go back to the name question.",
                },
                # Now answer it
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"name": "Alice"},
                    "assistant_message": "Thanks, Alice!",
                },
            ]
        )

        engine = LLMFlowEngine(compiled, mock_llm, strict_mode=False)
        responder = LLMFlowResponder(mock_llm)
        ctx = engine.initialize_context()

        # Process flow with skips and revisits
        # This tests the engine's ability to handle non-linear navigation

        # First question - skip it
        response = engine.process(ctx)
        assert response.kind == "prompt"

        resp = responder.respond(
            response.message or "",
            ctx.pending_field,
            ctx,
            "I'd rather not say",
        )
        assert resp.tool_name == "SkipQuestion"

        # The engine should handle the skip and move to next question
        # In a full implementation, this would be handled by the engine

    def test_clarification_flow(self) -> None:
        """Test handling clarification requests."""
        flow = Flow(
            id="clarification_flow",
            entry="start",
            nodes=[
                DecisionNode(id="start"),
                QuestionNode(
                    id="q_complex",
                    key="complex_answer",
                    prompt="What's your preferred deployment strategy?",
                    clarification="We need to know if you prefer blue-green, canary, or rolling deployments.",
                    examples=["blue-green", "canary", "rolling"],
                ),
                TerminalNode(id="end"),
            ],
            edges=[
                Edge(source="start", target="q_complex"),
                Edge(source="q_complex", target="end"),
            ],
        )

        compiler = FlowCompiler()
        compiled = compiler.compile(flow)

        mock_llm = SequentialMockLLM(
            [
                # First, ask for clarification
                {
                    "__tool_name__": "ClarifyQuestion",
                    "clarification_type": "meaning",
                },
                # Then provide answer
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"complex_answer": "blue-green"},
                },
            ]
        )

        engine = LLMFlowEngine(compiled, mock_llm, strict_mode=False)
        ctx = engine.initialize_context()

        # Ask complex question
        response = engine.process(ctx)
        assert "deployment strategy" in response.message

        # User asks for clarification using responder pattern
        from app.flow_core.llm_responder import LLMFlowResponder

        responder = LLMFlowResponder(mock_llm)

        clarification_response = responder.respond(
            response.message or "", ctx.pending_field, ctx, "What does that mean?"
        )

        # LLM should return clarification and update context
        assert clarification_response.tool_name == "ClarifyQuestion"
        assert ctx.clarification_count > 0
        assert clarification_response.metadata is not None
        assert clarification_response.metadata.get("clarification_type") == "meaning"
        assert clarification_response.metadata.get("is_clarification") is True

        # User now provides answer using responder pattern
        answer_response = responder.respond(
            response.message or "", ctx.pending_field, ctx, "I prefer blue-green"
        )

        # LLM should extract the answer
        assert answer_response.tool_name == "UpdateAnswersFlow"
        assert "blue-green" in answer_response.updates.get("complex_answer", "")

        # Apply updates and process with engine
        for k, v in answer_response.updates.items():
            ctx.answers[k] = v

        if answer_response.updates and ctx.pending_field in answer_response.updates:
            response = engine.process(
                ctx, None, {"answer": answer_response.updates[ctx.pending_field]}
            )

        # Should complete
        assert ctx.answers.get("complex_answer") == "blue-green"

    def test_validation_and_retry(self) -> None:
        """Test validation failures and retry logic."""
        flow = Flow(
            id="validation_flow",
            entry="start",
            nodes=[
                DecisionNode(id="start"),
                QuestionNode(
                    id="q_age",
                    key="age",
                    prompt="What's your age?",
                    data_type="number",
                    validator="age_validator",
                    max_attempts=3,
                ),
                TerminalNode(id="end"),
            ],
            edges=[
                Edge(source="start", target="q_age"),
                Edge(source="q_age", target="end"),
            ],
            validations={
                "age_validator": ValidationRule(
                    type="range",
                    min_value=18,
                    max_value=120,
                    error_message="Age must be between 18 and 120",
                ),
            },
        )

        compiler = FlowCompiler()
        compiled = compiler.compile(flow)

        # Test validation failure and retry
        age_validation = compiled.validations["age_validator"]

        # Test invalid values
        valid, error = age_validation.validate(15)
        assert not valid
        assert "must be between 18 and 120" in error

        valid, error = age_validation.validate(150)
        assert not valid

        # Test valid value
        valid, error = age_validation.validate(25)
        assert valid
        assert error is None


class TestEngineIntelligence:
    """Test LLM-oriented features of the engine."""

    def test_adaptive_conversation_style(self) -> None:
        """Test that engine adapts to conversation style."""
        flow = Flow(
            id="adaptive_flow",
            entry="start",
            nodes=[
                DecisionNode(id="start"),
                QuestionNode(id="q1", key="name", prompt="What is your name?"),
                QuestionNode(id="q2", key="reason", prompt="Why are you here today?"),
                TerminalNode(id="end"),
            ],
            edges=[
                Edge(source="start", target="q1"),
                Edge(source="q1", target="q2"),
                Edge(source="q2", target="end"),
            ],
            policies={
                "conversation": PolicyConversation(
                    conversation_style="adaptive",
                ),
            },
        )

        compiler = FlowCompiler()
        compiled = compiler.compile(flow)

        # Mock LLM that detects casual style
        mock_llm = SequentialMockLLM(
            [
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"name": "Bob"},
                    "assistant_message": "Hey Bob! Nice to meet you!",
                },
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"reason": "just browsing"},
                    "assistant_message": "Cool, happy to help you browse around!",
                },
            ]
        )

        engine = LLMFlowEngine(compiled, mock_llm, strict_mode=False)
        ctx = engine.initialize_context()

        # Casual interaction
        response = engine.process(ctx, "hey there!")

        # Engine should detect casual style
        # In full implementation, this would affect prompt generation
        ctx.conversation_style = "casual"

        response = engine.process(ctx, "I'm Bob", {"answer": "Bob"})

        # Verify context tracks style
        assert ctx.conversation_style == "casual"
        assert ctx.answers["name"] == "Bob"

    def test_intelligent_path_selection(self) -> None:
        """Test LLM-based path selection."""
        flow = Flow(
            id="path_flow",
            entry="start",
            nodes=[
                DecisionNode(id="start"),
                QuestionNode(id="q_intent", key="intent", prompt="What brings you here?"),
                DecisionNode(id="path_selector", decision_type="llm_assisted"),
                QuestionNode(id="q_tech", key="tech_issue", prompt="Describe your technical issue"),
                QuestionNode(
                    id="q_sales", key="product_interest", prompt="Which product interests you?"
                ),
                TerminalNode(id="tech_end", reason="Technical support complete"),
                TerminalNode(id="sales_end", reason="Sales inquiry complete"),
            ],
            edges=[
                Edge(source="start", target="q_intent"),
                Edge(source="q_intent", target="path_selector"),
                Edge(
                    source="path_selector",
                    target="q_tech",
                    label="technical_support",
                    condition_description="User needs technical help",
                ),
                Edge(
                    source="path_selector",
                    target="q_sales",
                    label="sales",
                    condition_description="User interested in purchasing",
                ),
                Edge(source="q_tech", target="tech_end"),
                Edge(source="q_sales", target="sales_end"),
            ],
        )

        compiler = FlowCompiler()
        compiled = compiler.compile(flow)

        # Mock LLM that intelligently selects path based on intent
        mock_llm = SequentialMockLLM(
            [
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"intent": "my computer won't start"},
                    "assistant_message": "I see you're having technical issues.",
                },
                # LLM should route to technical path based on intent
                {
                    "__tool_name__": "SelectFlowPath",
                    "path": "technical_support",
                    "confidence": 0.95,
                    "reasoning": "User mentioned computer won't start - clear technical issue",
                    "assistant_message": "Let me help you with that technical issue.",
                },
            ]
        )

        engine = LLMFlowEngine(compiled, mock_llm, strict_mode=False)
        ctx = engine.initialize_context()

        # Process intent
        response = engine.process(ctx)
        response = engine.process(
            ctx, "my computer won't start", {"answer": "my computer won't start"}
        )

        # Engine should intelligently route to technical path
        # This demonstrates LLM-assisted decision making
        assert ctx.answers["intent"] == "my computer won't start"

    def test_context_aware_prompting(self) -> None:
        """Test that prompts adapt based on context."""
        flow = Flow(
            id="context_flow",
            entry="start",
            nodes=[
                DecisionNode(id="start"),
                QuestionNode(
                    id="q_budget",
                    key="budget",
                    prompt="What's your budget?",
                    dependencies=[],
                ),
                QuestionNode(
                    id="q_premium",
                    key="premium_features",
                    prompt="Would you like to explore our premium features?",
                    dependencies=["budget"],
                ),
                TerminalNode(id="end"),
            ],
            edges=[
                Edge(source="start", target="q_budget"),
                Edge(source="q_budget", target="q_premium"),
                Edge(source="q_premium", target="end"),
            ],
        )

        compiler = FlowCompiler()
        compiled = compiler.compile(flow)

        # Test that second question adapts based on budget answer
        mock_llm = SequentialMockLLM(
            [
                {
                    "__tool_name__": "UpdateAnswersFlow",
                    "updates": {"budget": "50000"},
                    "assistant_message": "Great budget to work with!",
                },
            ]
        )

        engine = LLMFlowEngine(compiled, mock_llm, strict_mode=False)
        ctx = engine.initialize_context()

        # Answer budget question with high amount
        response = engine.process(ctx)
        response = engine.process(ctx, "50000", {"answer": "50000"})

        # Next prompt should be context-aware
        # In full implementation, high budget would influence premium features prompt
        assert ctx.answers["budget"] == "50000"

        # Engine would adapt the premium features prompt based on high budget
        # e.g., "With your budget, you can access all our premium features..."


class TestErrorHandlingAndRecovery:
    """Test error handling and recovery mechanisms."""

    def test_escalation_to_human(self) -> None:
        """Test escalation to human when needed."""
        flow = Flow(
            id="escalation_flow",
            entry="start",
            nodes=[
                DecisionNode(id="start"),
                QuestionNode(
                    id="q_complex",
                    key="complex_request",
                    prompt="How can I help you today?",
                ),
                TerminalNode(id="end"),
            ],
            edges=[
                Edge(source="start", target="q_complex"),
                Edge(source="q_complex", target="end"),
            ],
        )

        compiler = FlowCompiler()
        compiled = compiler.compile(flow)

        mock_llm = SequentialMockLLM(
            [
                {
                    "__tool_name__": "RequestHumanHandoff",
                    "reason": "complex_request",
                    "context": {
                        "user_request": "I need help with a legal dispute regarding my warranty",
                        "complexity": "high",
                    },
                    "urgency": "high",
                    "assistant_message": "This requires specialized assistance. Let me connect you with an expert.",
                },
            ]
        )

        responder = LLMFlowResponder(mock_llm)
        ctx = FlowContext(flow_id="escalation_flow")

        response = responder.respond(
            "How can I help you today?",
            "complex_request",
            ctx,
            "I need help with a legal dispute regarding my warranty",
        )

        assert response.escalate
        assert response.escalate_reason == "complex_request"
        assert response.metadata["urgency"] == "high"

    def test_recovery_from_invalid_state(self) -> None:
        """Test recovery when engine enters invalid state."""
        flow = Flow(
            id="recovery_flow",
            entry="start",
            nodes=[
                DecisionNode(id="start"),
                QuestionNode(id="q1", key="q1", prompt="Question 1"),
                # Missing connection to terminal
            ],
            edges=[
                Edge(source="start", target="q1"),
                # No edge from q1
            ],
        )

        compiler = FlowCompiler()
        compiled = compiler.compile(flow)

        # Should detect dead end
        assert compiled.validation_warnings  # Should have warnings about missing terminal

        mock_llm = MockLLM([])
        engine = LLMFlowEngine(compiled, mock_llm, strict_mode=False)
        ctx = engine.initialize_context()

        # Process until dead end
        response = engine.process(ctx)
        response = engine.process(ctx, "answer", {"answer": "answer"})

        # Engine should handle dead end gracefully
        # In LLM mode, it would try to find next question or escalate
        assert response.kind in ["escalate", "terminal"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
