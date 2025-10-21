"""Enhanced compiler for Flow IR with validation and optimization."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from .guards import DEFAULT_GUARDS, GuardFunction
from .ir import (
    ActionNode,
    DecisionNode,
    Flow,
    Node,
    QuestionNode,
    SubflowNode,
    TerminalNode,
    ValidationRule,
)


class CompiledEdge(BaseModel):
    """Compiled edge with resolved guard function."""

    source: str
    target: str
    guard_fn: GuardFunction | None = None
    guard_args: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    label: str | None = None
    condition_description: str | None = None


class CompiledValidation:
    """Compiled validation rule."""

    def __init__(self, rule: ValidationRule) -> None:
        self.rule = rule
        self._compiled_regex = None
        if rule.type == "regex" and rule.pattern:
            self._compiled_regex = re.compile(rule.pattern)

    def validate(self, value: Any) -> tuple[bool, str | None]:
        """Validate a value against the rule."""
        try:
            if self.rule.type == "regex":
                if not self._compiled_regex:
                    return True, None
                if not isinstance(value, str):
                    return False, "Value must be a string"
                if not self._compiled_regex.match(value):
                    return (
                        False,
                        self.rule.error_message
                        or f"Value does not match pattern: {self.rule.pattern}",
                    )

            elif self.rule.type == "range":
                try:
                    num_value = float(value)
                except (TypeError, ValueError):
                    return False, "Value must be a number"

                if self.rule.min_value is not None and num_value < self.rule.min_value:
                    return (
                        False,
                        self.rule.error_message or f"Value must be >= {self.rule.min_value}",
                    )
                if self.rule.max_value is not None and num_value > self.rule.max_value:
                    return (
                        False,
                        self.rule.error_message or f"Value must be <= {self.rule.max_value}",
                    )

            elif self.rule.type == "length":
                if not isinstance(value, str | list | dict):
                    return False, "Value must be a string, list, or dict"

                length = len(value)
                if self.rule.min_length is not None and length < self.rule.min_length:
                    return (
                        False,
                        self.rule.error_message or f"Length must be >= {self.rule.min_length}",
                    )
                if self.rule.max_length is not None and length > self.rule.max_length:
                    return (
                        False,
                        self.rule.error_message or f"Length must be <= {self.rule.max_length}",
                    )

            elif self.rule.type == "custom":
                # Custom validation would be implemented via a registry
                return True, None

            return True, None

        except Exception as e:
            return False, f"Validation error: {e!s}"


class CompiledFlow(BaseModel):
    """Compiled flow with resolved references and optimizations."""

    model_config = {"arbitrary_types_allowed": True}

    id: str
    entry: str
    nodes: dict[str, Node]
    edges_from: dict[str, list[CompiledEdge]]
    edges_to: dict[str, list[CompiledEdge]]
    validations: dict[str, CompiledValidation] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    policies: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    subflows: dict[str, CompiledFlow] = Field(default_factory=dict)

    # Optimization: pre-computed structures
    question_nodes: list[str] = Field(default_factory=list)
    decision_nodes: list[str] = Field(default_factory=list)
    terminal_nodes: list[str] = Field(default_factory=list)
    action_nodes: list[str] = Field(default_factory=list)
    subflow_nodes: list[str] = Field(default_factory=list)

    # Validation results
    has_unreachable_nodes: bool = False
    has_cycles: bool = False
    validation_warnings: list[str] = Field(default_factory=list)


class FlowCompiler:
    """Enhanced compiler with validation and optimization."""

    def __init__(self, guard_registry: dict[str, GuardFunction] | None = None) -> None:
        self.guard_registry = guard_registry or DEFAULT_GUARDS
        self.validation_errors: list[str] = []
        self.validation_warnings: list[str] = []

    def compile(self, flow: Flow) -> CompiledFlow:
        """Compile a Flow IR into an optimized CompiledFlow."""
        self.validation_errors = []
        self.validation_warnings = []

        # Validate flow structure
        self._validate_flow(flow)

        if self.validation_errors:
            raise ValueError("Flow compilation failed:\n" + "\n".join(self.validation_errors))

        # Build node map
        node_map = {n.id: n for n in flow.nodes}

        # Compile edges
        edges_from: dict[str, list[CompiledEdge]] = {}
        edges_to: dict[str, list[CompiledEdge]] = {}

        for edge in flow.edges:
            compiled_edge = self._compile_edge(edge)
            edges_from.setdefault(edge.source, []).append(compiled_edge)
            edges_to.setdefault(edge.target, []).append(compiled_edge)

        # Sort edges by priority for deterministic evaluation
        for edges in edges_from.values():
            edges.sort(key=lambda e: e.priority)

        # Compile validations
        compiled_validations = {}
        for key, rule in flow.validations.items():
            compiled_validations[key] = CompiledValidation(rule)

        # Compile subflows recursively
        compiled_subflows = {}
        for name, subflow in flow.subflows.items():
            compiled_subflows[name] = self.compile(subflow)

        # Categorize nodes for optimization
        question_nodes = []
        decision_nodes = []
        terminal_nodes = []
        action_nodes = []
        subflow_nodes = []

        for node_id, node in node_map.items():
            if isinstance(node, QuestionNode):
                question_nodes.append(node_id)
            elif isinstance(node, DecisionNode):
                decision_nodes.append(node_id)
            elif isinstance(node, TerminalNode):
                terminal_nodes.append(node_id)
            elif isinstance(node, ActionNode):
                action_nodes.append(node_id)
            elif isinstance(node, SubflowNode):
                subflow_nodes.append(node_id)

        # Check for unreachable nodes and cycles
        has_unreachable = self._check_unreachable_nodes(flow.entry, edges_from, node_map)
        has_cycles = self._detect_cycles(edges_from)

        # Build compiled flow
        compiled = CompiledFlow(
            id=flow.id,
            entry=flow.entry,
            nodes=node_map,
            edges_from=edges_from,
            edges_to=edges_to,
            validations=compiled_validations,
            metadata=flow.metadata.model_dump() if flow.metadata else {},
            policies=flow.policies.model_dump(),
            context=flow.context,
            subflows=compiled_subflows,
            question_nodes=question_nodes,
            decision_nodes=decision_nodes,
            terminal_nodes=terminal_nodes,
            action_nodes=action_nodes,
            subflow_nodes=subflow_nodes,
            has_unreachable_nodes=has_unreachable,
            has_cycles=has_cycles,
            validation_warnings=self.validation_warnings,
        )

        return compiled

    def _validate_flow(self, flow: Flow) -> None:
        """Validate flow structure and references."""
        # Check entry node exists
        if not flow.node_by_id(flow.entry):
            self.validation_errors.append(f"Entry node '{flow.entry}' not found")

        # Build node ID set for reference checking
        node_ids = {n.id for n in flow.nodes}

        # Check for duplicate node IDs
        seen_ids = set()
        for node in flow.nodes:
            if node.id in seen_ids:
                self.validation_errors.append(f"Duplicate node ID: '{node.id}'")
            seen_ids.add(node.id)

        # Validate edges
        for edge in flow.edges:
            if edge.source not in node_ids:
                self.validation_errors.append(f"Edge source '{edge.source}' not found")
            if edge.target not in node_ids:
                self.validation_errors.append(f"Edge target '{edge.target}' not found")

            # Validate guard references
            if edge.guard and edge.guard.fn not in self.guard_registry:
                self.validation_warnings.append(
                    f"Unknown guard function '{edge.guard.fn}' in edge {edge.source} -> {edge.target}"
                )

        # Validate question node dependencies
        question_keys = set()
        for node in flow.nodes:
            if isinstance(node, QuestionNode):
                question_keys.add(node.key)

        for node in flow.nodes:
            if isinstance(node, QuestionNode):
                for dep in node.dependencies:
                    if dep not in question_keys:
                        self.validation_warnings.append(
                            f"Question '{node.key}' depends on unknown key '{dep}'"
                        )

        # Validate subflow references
        for node in flow.nodes:
            if isinstance(node, SubflowNode):
                if node.flow_ref not in flow.subflows:
                    self.validation_errors.append(
                        f"Subflow node '{node.id}' references unknown flow '{node.flow_ref}'"
                    )

        # Check for at least one terminal node
        has_terminal = any(isinstance(n, TerminalNode) for n in flow.nodes)
        if not has_terminal:
            self.validation_warnings.append("Flow has no terminal nodes")

    def _compile_edge(self, edge: Any) -> CompiledEdge:
        """Compile an edge with guard resolution."""
        guard_fn = None
        guard_args = {}

        if edge.guard:
            guard_fn = self.guard_registry.get(edge.guard.fn)
            guard_args = dict(edge.guard.args)

        return CompiledEdge(
            source=edge.source,
            target=edge.target,
            guard_fn=guard_fn,
            guard_args=guard_args,
            priority=edge.priority,
            label=edge.label,
            condition_description=edge.condition_description,
        )

    def _check_unreachable_nodes(
        self,
        entry: str,
        edges_from: dict[str, list[CompiledEdge]],
        nodes: dict[str, Node],
    ) -> bool:
        """Check for unreachable nodes using BFS."""
        visited = set()
        queue = [entry]

        while queue:
            node_id = queue.pop(0)
            if node_id in visited:
                continue

            visited.add(node_id)

            # Add all targets of outgoing edges
            for edge in edges_from.get(node_id, []):
                if edge.target not in visited:
                    queue.append(edge.target)

        unreachable = set(nodes.keys()) - visited
        if unreachable:
            self.validation_warnings.append(
                f"Unreachable nodes detected: {', '.join(sorted(unreachable))}"
            )
            return True

        return False

    def _detect_cycles(self, edges_from: dict[str, list[CompiledEdge]]) -> bool:
        """Detect cycles in the flow graph using DFS."""
        visited = set()
        rec_stack = set()

        def has_cycle(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)

            for edge in edges_from.get(node_id, []):
                if edge.target not in visited:
                    if has_cycle(edge.target):
                        return True
                elif edge.target in rec_stack:
                    return True

            rec_stack.remove(node_id)
            return False

        for node_id in edges_from:
            if node_id not in visited:
                if has_cycle(node_id):
                    self.validation_warnings.append("Cycle detected in flow graph")
                    return True

        return False


def compile_flow(
    flow: Flow, guard_registry: dict[str, GuardFunction] | None = None
) -> CompiledFlow:
    """Convenience function to compile a flow."""
    compiler = FlowCompiler(guard_registry)
    return compiler.compile(flow)
