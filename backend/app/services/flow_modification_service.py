"""Flow modification service with batch action support.

This module implements a clean, single-responsibility service for modifying flows
using batch actions from the LLM in a single tool call.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypedDict
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import repository
from app.flow_core.compiler import FlowCompiler
from app.flow_core.ir import Flow as FlowIR

logger = logging.getLogger(__name__)


class ActionType(str, Enum):
    """Types of actions that can be performed on a flow."""

    ADD_NODE = "add_node"
    UPDATE_NODE = "update_node"
    DELETE_NODE = "delete_node"
    ADD_EDGE = "add_edge"
    UPDATE_EDGE = "update_edge"
    DELETE_EDGE = "delete_edge"
    SET_ENTRY = "set_entry"


class FlowAction(TypedDict, total=False):
    """Single action to perform on a flow."""

    action: ActionType
    node_id: str | None
    edge_id: str | None
    node_definition: dict[str, Any] | None
    updates: dict[str, Any] | None
    source: str | None
    target: str | None
    priority: int | None
    guard: dict[str, Any] | None
    condition_description: str | None
    entry_node: str | None


class BatchFlowActionsRequest(BaseModel):
    """Request containing multiple flow modification actions to execute atomically."""

    actions: list[FlowAction] = Field(
        description="Array of actions to perform on the flow. All actions are executed in order."
    )


@dataclass
class ActionResult:
    """Result of executing a single action."""

    action_type: ActionType
    success: bool
    message: str
    error: str | None = None


@dataclass
class BatchActionResult:
    """Result of executing a batch of actions."""

    success: bool
    modified_flow: dict[str, Any] | None
    action_results: list[ActionResult]
    error: str | None = None


class FlowModificationService:
    """Service for executing batch flow modifications atomically.

    This service follows single responsibility principle - it only handles
    the execution of flow modification actions. It doesn't know about LLMs,
    prompts, or chat interfaces.
    """

    def __init__(self, session: Session | None = None):
        """Initialize the service with optional database session."""
        self.session = session

    def execute_batch_actions(
        self,
        flow: dict[str, Any],
        actions: list[FlowAction],
        flow_id: UUID | None = None,
        persist: bool = True,
    ) -> BatchActionResult:
        """Execute a batch of actions on a flow atomically.

        Args:
            flow: Current flow definition
            actions: List of actions to execute
            flow_id: Optional flow ID for persistence
            persist: Whether to persist changes to database

        Returns:
            BatchActionResult with success status and modified flow
        """
        if not actions:
            return BatchActionResult(
                success=False, modified_flow=None, action_results=[], error="No actions provided"
            )

        # Work on a deep copy to ensure atomicity of nested structures (nodes/edges)
        working_flow = copy.deepcopy(flow)
        action_results = []

        logger.info("=" * 80)
        logger.info("🔧 FLOW MODIFICATION SERVICE: Executing batch actions")
        logger.info("=" * 80)
        logger.info(f"Flow ID: {flow_id}")
        logger.info(f"Actions count: {len(actions)}")
        logger.info(f"Persist: {persist}")
        logger.info("=" * 80)

        for i, action in enumerate(actions):
            try:
                action_type = ActionType(action.get("action", ""))
                logger.info(f"Action {i + 1}/{len(actions)}: {action_type.value}")

                result = self._execute_single_action(working_flow, action)
                action_results.append(result)

                if not result.success:
                    logger.error(
                        f"Action {i + 1} failed: {result.error}. Rolling back all changes."
                    )
                    return BatchActionResult(
                        success=False,
                        modified_flow=None,
                        action_results=action_results,
                        error=f"Action {i + 1} ({action_type.value}) failed: {result.error}",
                    )

            except Exception as e:
                logger.error(f"Unexpected error executing action {i + 1}: {e}", exc_info=True)
                action_results.append(
                    ActionResult(
                        action_type=action.get("action", "unknown"),
                        success=False,
                        message="",
                        error=str(e),
                    )
                )
                return BatchActionResult(
                    success=False,
                    modified_flow=None,
                    action_results=action_results,
                    error=f"Unexpected error in action {i + 1}: {e!s}",
                )

        # Validate the modified flow
        validation_result = self._validate_flow(working_flow)
        if not validation_result.success:
            logger.error(f"Flow validation failed after modifications: {validation_result.error}")
            return BatchActionResult(
                success=False,
                modified_flow=None,
                action_results=action_results,
                error=f"Flow validation failed: {validation_result.error}",
            )

        # Persist if requested and we have the necessary context
        if persist and flow_id and self.session:
            logger.info(f"💾 Attempting to persist flow {flow_id} to database...")
            try:
                self._persist_flow(working_flow, flow_id)
                logger.info("=" * 80)
                logger.info("✅ FLOW PERSISTED SUCCESSFULLY")
                logger.info("=" * 80)
                logger.info(f"Flow ID: {flow_id}")
                logger.info(f"Modifications applied: {len(actions)}")
                logger.info("=" * 80)
            except Exception as e:
                logger.error("=" * 80)
                logger.error("❌ FLOW PERSISTENCE FAILED")
                logger.error("=" * 80)
                logger.error(f"Flow ID: {flow_id}")
                logger.error(f"Error: {e}", exc_info=True)
                logger.error("=" * 80)
                return BatchActionResult(
                    success=False,
                    modified_flow=None,
                    action_results=action_results,
                    error=f"Failed to persist flow: {e!s}",
                )
        elif persist and not flow_id:
            logger.warning("⚠️ Persist requested but no flow_id provided")
        elif persist and not self.session:
            logger.warning("⚠️ Persist requested but no database session available")

        return BatchActionResult(
            success=True, modified_flow=working_flow, action_results=action_results, error=None
        )

    def _execute_single_action(self, flow: dict[str, Any], action: FlowAction) -> ActionResult:
        """Execute a single action on the flow (mutates flow in place)."""
        action_type = ActionType(action.get("action", ""))

        try:
            if action_type == ActionType.ADD_NODE:
                return self._add_node(flow, action)
            if action_type == ActionType.UPDATE_NODE:
                return self._update_node(flow, action)
            if action_type == ActionType.DELETE_NODE:
                return self._delete_node(flow, action)
            if action_type == ActionType.ADD_EDGE:
                return self._add_edge(flow, action)
            if action_type == ActionType.UPDATE_EDGE:
                return self._update_edge(flow, action)
            if action_type == ActionType.DELETE_EDGE:
                return self._delete_edge(flow, action)
            if action_type == ActionType.SET_ENTRY:
                return self._set_entry(flow, action)
            return ActionResult(
                action_type=action_type,
                success=False,
                message="",
                error=f"Unknown action type: {action_type}",
            )
        except Exception as e:
            logger.error(f"Error executing {action_type.value}: {e}", exc_info=True)
            return ActionResult(action_type=action_type, success=False, message="", error=str(e))

    def _add_node(self, flow: dict[str, Any], action: FlowAction) -> ActionResult:
        """Add a node to the flow."""
        node_def = action.get("node_definition")
        if not node_def:
            return ActionResult(
                action_type=ActionType.ADD_NODE,
                success=False,
                message="",
                error="node_definition is required for add_node action",
            )

        node_id = node_def.get("id")
        if not node_id:
            return ActionResult(
                action_type=ActionType.ADD_NODE,
                success=False,
                message="",
                error="node_definition must include 'id' field",
            )

        nodes = flow.setdefault("nodes", [])

        # Check if node already exists
        if any(n.get("id") == node_id for n in nodes):
            return ActionResult(
                action_type=ActionType.ADD_NODE,
                success=False,
                message="",
                error=f"Node '{node_id}' already exists",
            )

        nodes.append(node_def)

        return ActionResult(
            action_type=ActionType.ADD_NODE,
            success=True,
            message=f"Added node '{node_id}'",
            error=None,
        )

    def _update_node(self, flow: dict[str, Any], action: FlowAction) -> ActionResult:
        """Update an existing node in the flow."""
        node_id = action.get("node_id")
        updates = action.get("updates", {})

        if not node_id:
            return ActionResult(
                action_type=ActionType.UPDATE_NODE,
                success=False,
                message="",
                error="node_id is required for update_node action",
            )

        nodes = flow.get("nodes", [])
        node_found = False

        for node in nodes:
            if node.get("id") == node_id:
                # Merge updates with existing node, prioritizing new values
                node.update(updates)
                node_found = True
                break

        if not node_found:
            return ActionResult(
                action_type=ActionType.UPDATE_NODE,
                success=False,
                message="",
                error=f"Node '{node_id}' not found",
            )

        return ActionResult(
            action_type=ActionType.UPDATE_NODE,
            success=True,
            message=f"Updated node '{node_id}'",
            error=None,
        )

    def _delete_node(self, flow: dict[str, Any], action: FlowAction) -> ActionResult:
        """Delete a node and its connected edges from the flow."""
        node_id = action.get("node_id")

        if not node_id:
            return ActionResult(
                action_type=ActionType.DELETE_NODE,
                success=False,
                message="",
                error="node_id is required for delete_node action",
            )

        nodes = flow.get("nodes", [])
        edges = flow.get("edges", [])

        # Remove the node
        original_count = len(nodes)
        flow["nodes"] = [n for n in nodes if n.get("id") != node_id]

        if len(flow["nodes"]) == original_count:
            return ActionResult(
                action_type=ActionType.DELETE_NODE,
                success=False,
                message="",
                error=f"Node '{node_id}' not found",
            )

        # Remove all edges connected to this node
        flow["edges"] = [
            e for e in edges if e.get("source") != node_id and e.get("target") != node_id
        ]

        return ActionResult(
            action_type=ActionType.DELETE_NODE,
            success=True,
            message=f"Deleted node '{node_id}' and its edges",
            error=None,
        )

    def _add_edge(self, flow: dict[str, Any], action: FlowAction) -> ActionResult:
        """Add an edge to the flow."""
        source = action.get("source")
        target = action.get("target")

        if not source or not target:
            return ActionResult(
                action_type=ActionType.ADD_EDGE,
                success=False,
                message="",
                error="source and target are required for add_edge action",
            )

        edges = flow.setdefault("edges", [])

        # Check if edge already exists
        if any(e.get("source") == source and e.get("target") == target for e in edges):
            return ActionResult(
                action_type=ActionType.ADD_EDGE,
                success=False,
                message="",
                error=f"Edge from '{source}' to '{target}' already exists",
            )

        new_edge = {"source": source, "target": target}

        # Add optional fields if provided
        if action.get("priority") is not None:
            new_edge["priority"] = action["priority"]
        if action.get("guard"):
            new_edge["guard"] = action["guard"]
        if action.get("condition_description"):
            new_edge["condition_description"] = action["condition_description"]

        edges.append(new_edge)

        return ActionResult(
            action_type=ActionType.ADD_EDGE,
            success=True,
            message=f"Added edge from '{source}' to '{target}'",
            error=None,
        )

    def _update_edge(self, flow: dict[str, Any], action: FlowAction) -> ActionResult:
        """Update an existing edge in the flow."""
        source = action.get("source")
        target = action.get("target")
        updates = action.get("updates", {})

        if not source or not target:
            return ActionResult(
                action_type=ActionType.UPDATE_EDGE,
                success=False,
                message="",
                error="source and target are required for update_edge action",
            )

        edges = flow.get("edges", [])
        edge_found = False

        for edge in edges:
            if edge.get("source") == source and edge.get("target") == target:
                edge.update(updates)
                edge_found = True
                break

        if not edge_found:
            return ActionResult(
                action_type=ActionType.UPDATE_EDGE,
                success=False,
                message="",
                error=f"Edge from '{source}' to '{target}' not found",
            )

        return ActionResult(
            action_type=ActionType.UPDATE_EDGE,
            success=True,
            message=f"Updated edge from '{source}' to '{target}'",
            error=None,
        )

    def _delete_edge(self, flow: dict[str, Any], action: FlowAction) -> ActionResult:
        """Delete an edge from the flow."""
        source = action.get("source")
        target = action.get("target")

        if not source or not target:
            return ActionResult(
                action_type=ActionType.DELETE_EDGE,
                success=False,
                message="",
                error="source and target are required for delete_edge action",
            )

        edges = flow.get("edges", [])
        original_count = len(edges)

        flow["edges"] = [
            e for e in edges if not (e.get("source") == source and e.get("target") == target)
        ]

        if len(flow["edges"]) == original_count:
            return ActionResult(
                action_type=ActionType.DELETE_EDGE,
                success=False,
                message="",
                error=f"Edge from '{source}' to '{target}' not found",
            )

        return ActionResult(
            action_type=ActionType.DELETE_EDGE,
            success=True,
            message=f"Deleted edge from '{source}' to '{target}'",
            error=None,
        )

    def _validate_flow(self, flow: dict[str, Any]) -> ActionResult:
        """Validate the flow definition."""
        try:
            flow_ir = FlowIR.model_validate(flow)
            compiler = FlowCompiler()
            compiled = compiler.compile(flow_ir)

            if hasattr(compiled, "validation_errors") and compiled.validation_errors:
                return ActionResult(
                    action_type="validate",
                    success=False,
                    message="",
                    error="; ".join(compiled.validation_errors),
                )

            if hasattr(compiled, "errors") and compiled.errors:
                return ActionResult(
                    action_type="validate",
                    success=False,
                    message="",
                    error="; ".join(compiled.errors),
                )

            return ActionResult(
                action_type="validate",
                success=True,
                message="Flow validation successful",
                error=None,
            )
        except Exception as e:
            return ActionResult(action_type="validate", success=False, message="", error=str(e))

    def _set_entry(self, flow: dict[str, Any], action: FlowAction) -> ActionResult:
        """Set the entry point of the flow."""
        entry_node = action.get("entry_node")

        if not entry_node:
            return ActionResult(
                action_type=ActionType.SET_ENTRY,
                success=False,
                message="",
                error="entry_node is required for set_entry action",
            )

        # Verify the node exists
        nodes = flow.get("nodes", [])
        if not any(n.get("id") == entry_node for n in nodes):
            return ActionResult(
                action_type=ActionType.SET_ENTRY,
                success=False,
                message="",
                error=f"Node '{entry_node}' not found in flow",
            )

        flow["entry"] = entry_node

        return ActionResult(
            action_type=ActionType.SET_ENTRY,
            success=True,
            message=f"Set entry point to '{entry_node}'",
            error=None,
        )

    def _persist_flow(self, flow: dict[str, Any], flow_id: UUID) -> None:
        """Persist the flow to the database."""
        if not self.session:
            raise RuntimeError("No database session available for persistence")

        node_count = len(flow.get("nodes", []))
        edge_count = len(flow.get("edges", []))

        logger.info(f"📝 Calling repository.update_flow_with_versioning for flow {flow_id}")
        logger.info(f"   Nodes: {node_count}, Edges: {edge_count}")

        try:
            repository.update_flow_with_versioning(
                self.session,
                flow_id=flow_id,
                new_definition=flow,
                change_description=f"Batch modification: {node_count} nodes, {edge_count} edges",
                created_by="flow_chat_agent",
            )
            logger.info(f"✅ Repository update successful for flow {flow_id}")
        except Exception as e:
            logger.error(f"❌ Repository update failed: {e}", exc_info=True)
            raise
