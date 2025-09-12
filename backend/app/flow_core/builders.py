from __future__ import annotations

from typing import Any

from .config_types import FlowBuildConfig, QuestionConfig
from .ir import DecisionNode, Edge, Flow, GuardRef, QuestionNode, TerminalNode


def build_flow_from_questions(questions: list[QuestionConfig], flow_id: str) -> Flow:
    """Build a simple questionnaire-style Flow from typed question configs."""
    chooser = DecisionNode(id="choose_next", label="choose_next")
    terminal = TerminalNode(id="done", label="done", reason="checklist_complete")
    nodes: list[Any] = [chooser, terminal]

    # Question nodes
    for q in questions:
        nodes.append(
            QuestionNode(id=f"q:{q.key}", label=q.key, key=q.key, prompt=q.prompt)
        )

    # Edges
    edges: list[Edge] = []
    for q in sorted(questions, key=lambda it: it.priority):
        guard = GuardRef(
            fn="deps_missing", args={"key": q.key, "dependencies": q.dependencies}
        )
        edges.append(
            Edge(source=chooser.id, target=f"q:{q.key}", guard=guard, priority=q.priority)
        )

    edges.append(
        Edge(source=chooser.id, target=terminal.id, guard=GuardRef(fn="always"), priority=10_000)
    )
    for q in questions:
        edges.append(
            Edge(source=f"q:{q.key}", target=chooser.id, guard=GuardRef(fn="always"), priority=0)
        )

    return Flow(id=flow_id, entry=chooser.id, nodes=nodes, edges=edges)


def build_flow_from_config(config: FlowBuildConfig) -> Flow:
    """Build a flow from typed configuration."""
    return build_flow_from_questions(config.questions, config.flow_id)


def build_flow_from_question_graph_params(params: dict[str, Any], flow_id: str) -> Flow:
    """Convert raw parameters to typed config and build flow."""
    # Extract basic info
    flow_id_param = params.get("flow_id", flow_id)
    if not isinstance(flow_id_param, str):
        flow_id_param = str(flow_id_param)

    # Handle different question formats
    questions_data = []

    # Check for question_graph format
    question_graph = params.get("question_graph")
    if isinstance(question_graph, dict):
        # Handle { global: [...], paths?: {...} } format
        global_questions = question_graph.get("global", [])
        if isinstance(global_questions, list):
            questions_data = global_questions
    elif isinstance(question_graph, list):
        # Handle direct list format
        questions_data = question_graph
    else:
        # Check for direct questions list
        questions_raw = params.get("questions", [])
        if isinstance(questions_raw, list):
            questions_data = questions_raw

    # Convert to QuestionConfig objects
    questions = []
    for q_data in questions_data:
        if not isinstance(q_data, dict):
            continue

        try:
            question = QuestionConfig(
                key=str(q_data.get("key", "")).strip(),
                prompt=str(q_data.get("prompt", "")).strip(),
                priority=int(q_data.get("priority", 100)),
                dependencies=[str(d) for d in q_data.get("dependencies", [])],
                required=bool(q_data.get("required", True)),
                validation_type=q_data.get("validation_type"),
                allowed_values=q_data.get("allowed_values"),
                input_type=str(q_data.get("input_type", "text")),
                placeholder=q_data.get("placeholder"),
                help_text=q_data.get("help_text")
            )
            if question.key and question.prompt:  # Only add valid questions
                questions.append(question)
        except (ValueError, TypeError):
            # Skip invalid questions
            continue

    # If already given as Flow IR under key 'flow', validate via model
    flow_raw = params.get("flow") if isinstance(params, dict) else None
    if isinstance(flow_raw, dict):
        return Flow.model_validate(flow_raw)  # type: ignore[no-any-return]

    # Create typed config and build
    config = FlowBuildConfig(
        flow_id=flow_id_param,
        questions=questions,
        title=params.get("title"),
        description=params.get("description"),
        version=str(params.get("version", "1.0")),
        allow_skip=bool(params.get("allow_skip", False)),
        require_all_answers=bool(params.get("require_all_answers", True)),
        completion_message=params.get("completion_message")
    )

    return build_flow_from_config(config)
