"""Tools for modifying flow definitions in the flow chat agent."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import repository
from app.flow_core.compiler import FlowCompiler
from app.flow_core.ir import Flow as FlowIR

logger = logging.getLogger(__name__)


class ToolResult(BaseModel):
    """Structured result from tool execution."""
    
    success: bool = Field(description="Whether the tool executed successfully")
    action: str = Field(description="The action performed (add_node, validate_flow, etc.)")
    message: str = Field(description="Human-readable message about the result")
    is_modification: bool = Field(default=False, description="Whether this was a flow modification")
    is_validation: bool = Field(default=False, description="Whether this was a validation/summary operation")
    should_continue: bool = Field(default=True, description="Whether the agent should continue with more iterations")
    
    def __str__(self) -> str:
        """Return the message for backward compatibility."""
        return self.message


class SetEntireFlowRequest(BaseModel):
    """Request to replace the entire flow definition."""
    
    flow_definition: Dict[str, Any] = Field(
        description="Complete flow definition JSON that will replace the current flow"
    )


class ValidateFlowRequest(BaseModel):
    """Request to validate the current flow definition."""
    pass


class GetFlowSummaryRequest(BaseModel):
    """Request to get a summary of the current flow."""
    pass


class AddNodeRequest(BaseModel):
    """Request to add a new node to the flow."""
    
    node_definition: Dict[str, Any] = Field(
        description="Complete node definition to add to the flow (with id, kind, and other properties)"
    )
    position_after: str | None = Field(
        default=None, 
        description="ID of the node after which to insert this node (optional)"
    )


class UpdateNodeRequest(BaseModel):
    """Request to update an existing node in the flow."""
    
    node_id: str = Field(description="ID of the node to update")
    updates: Dict[str, Any] = Field(
        description="Fields to update in the node (e.g., prompt, allowed_values). REQUIRED - cannot be empty."
    )


class DeleteNodeRequest(BaseModel):
    """Request to delete a node from the flow."""
    
    node_id: str = Field(description="ID of the node to delete")


class AddEdgeRequest(BaseModel):
    """Request to add a new edge to the flow."""
    
    source: str = Field(description="Source node ID")
    target: str = Field(description="Target node ID")
    priority: int = Field(default=0, description="Edge priority (lower = higher precedence)")
    guard: Dict[str, Any] | None = Field(default=None, description="Optional guard condition")
    condition_description: str | None = Field(default=None, description="Human-readable condition explanation")


class UpdateEdgeRequest(BaseModel):
    """Request to update an existing edge in the flow."""
    
    source: str = Field(description="Source node ID of the edge to update")
    target: str = Field(description="Target node ID of the edge to update") 
    updates: Dict[str, Any] = Field(
        description="Fields to update in the edge (e.g., priority, guard, condition_description). REQUIRED - cannot be empty."
    )


class DeleteEdgeRequest(BaseModel):
    """Request to delete an edge from the flow."""
    
    source: str = Field(description="Source node ID of the edge to delete")
    target: str = Field(description="Target node ID of the edge to delete")


def set_entire_flow(flow_definition: Dict[str, Any], flow_id: UUID | None = None, session: Session | None = None) -> ToolResult:
    """Replace the entire flow definition with a new one.
    
    This is the primary tool for setting complete flows from scratch,
    especially when users provide WhatsApp conversations or want complete rewrites.
    """
    try:
        logger.info(f"set_entire_flow called: flow_id={flow_id}, session={'present' if session else 'None'}, nodes_count={len(flow_definition.get('nodes', []))}")
        
        # Check if we have the required parameters for persistence
        if not flow_id or not session:
            logger.warning("set_entire_flow called without flow_id or session - validation only")
            # Just validate without persisting
            flow_ir = FlowIR.model_validate(flow_definition)
            compiler = FlowCompiler()
            compiled = compiler.compile(flow_ir)
            
            if hasattr(compiled, 'validation_errors') and compiled.validation_errors:
                logger.error(f"set_entire_flow: Validation failed: {compiled.validation_errors}")
                return ToolResult(
                    success=False,
                    action="set_entire_flow",
                    message=f"Flow validation failed: {'; '.join(compiled.validation_errors)}",
                    is_modification=False
                )
            elif hasattr(compiled, 'errors') and compiled.errors:
                logger.error(f"set_entire_flow: Compilation failed: {compiled.errors}")
                return ToolResult(
                    success=False,
                    action="set_entire_flow", 
                    message=f"Flow validation failed: {'; '.join(compiled.errors)}",
                    is_modification=False
                )
            
            node_count = len(flow_definition.get('nodes', []))
            edge_count = len(flow_definition.get('edges', []))
            entry_point = flow_definition.get('entry', 'unknown')
            
            logger.info(f"set_entire_flow: Validation-only mode successful ({node_count} nodes, {edge_count} edges)")
            return ToolResult(
                success=True,
                action="set_entire_flow",
                message=(
                    f"Flow validation successful (not persisted):\n"
                    f"- Entry point: {entry_point}\n"
                    f"- Nodes: {node_count}\n" 
                    f"- Edges: {edge_count}\n"
                    f"- Flow ID: {flow_definition.get('id', 'unknown')}\n"
                    f"Note: Changes not saved - persistence requires database connection."
                ),
                is_modification=False
            )
        
        logger.info(f"set_entire_flow: Validating flow definition with {len(flow_definition.get('nodes', []))} nodes")
        
        # Validate the flow definition
        flow_ir = FlowIR.model_validate(flow_definition)
        compiler = FlowCompiler()
        compiled = compiler.compile(flow_ir)
        
        if hasattr(compiled, 'validation_errors') and compiled.validation_errors:
            logger.error(f"set_entire_flow: Flow validation failed: {compiled.validation_errors}")
            return ToolResult(
                success=False,
                action="set_entire_flow",
                message=f"Flow validation failed: {'; '.join(compiled.validation_errors)}",
                is_modification=False
            )
        elif hasattr(compiled, 'errors') and compiled.errors:
            logger.error(f"set_entire_flow: Flow compilation failed: {compiled.errors}")
            return ToolResult(
                success=False,
                action="set_entire_flow",
                message=f"Flow validation failed: {'; '.join(compiled.errors)}",
                is_modification=False
            )
        
        logger.info(f"set_entire_flow: Flow validation successful, persisting to database")
        
        # Persist to database with versioning
        # Log the specific node we're about to save to debug overwriting
        for node in flow_definition.get('nodes', []):
            if node.get('id') == 'q.intensidade_dor':
                logger.info(f"set_entire_flow: About to save q.intensidade_dor with allowed_values: {node.get('allowed_values')}")
                break
        
        logger.info(f"set_entire_flow: Calling repository.update_flow_with_versioning for flow {flow_id}")
        updated_flow = repository.update_flow_with_versioning(
            session,
            flow_id=flow_id,
            new_definition=flow_definition,
            change_description=f"Complete flow replacement with {len(flow_definition.get('nodes', []))} nodes",
            created_by="flow_chat_agent",
        )
        
        if not updated_flow:
            logger.error(f"set_entire_flow: repository.update_flow_with_versioning returned None - flow {flow_id} not found")
            return ToolResult(
                success=False,
                action="set_entire_flow",
                message=f"Failed to persist flow definition: Flow {flow_id} not found",
                is_modification=True
            )
        
        logger.info(f"set_entire_flow: Successfully updated flow {flow_id} in session, new version: {updated_flow.version}")
        logger.info(f"set_entire_flow: Flow will be committed by the service layer")
        
        # Return success message with summary
        node_count = len(flow_definition.get('nodes', []))
        edge_count = len(flow_definition.get('edges', []))
        entry_point = flow_definition.get('entry', 'unknown')
        
        logger.info("Successfully updated flow %s with %d nodes and %d edges", flow_id, node_count, edge_count)
        
        # Return structured success result
        success_msg = f"✅ Fluxo atualizado com sucesso! ({node_count} perguntas, {edge_count} conexões)"
        logger.info(f"set_entire_flow: Returning success message: {success_msg}")
        return ToolResult(
            success=True,
            action="set_entire_flow",
            message=success_msg,
            is_modification=True,
            should_continue=False  # Complete flow replacement usually means we're done
        )
        
    except Exception as e:
        logger.error("Failed to set flow definition for flow %s: %s", flow_id, str(e), exc_info=True)
        return ToolResult(
            success=False,
            action="set_entire_flow",
            message=f"Failed to set flow definition: {str(e)}",
            is_modification=False
        )


def add_node(flow_definition: Dict[str, Any], node_definition: Dict[str, Any], position_after: str | None = None, flow_id: UUID | None = None, session: Session | None = None) -> str:
    """Add a new node to the flow."""
    try:
        node_id = node_definition.get('id')
        node_kind = node_definition.get('kind')
        
        # Validate required fields
        if not node_id or not node_kind:
            return f"Node missing required fields: id={node_id}, kind={node_kind}"
        
        # Add node to flow
        nodes = flow_definition.get('nodes', [])
        
        # Check if node already exists
        if any(n.get('id') == node_id for n in nodes):
            return f"Node '{node_id}' already exists in flow"
        
        nodes.append(node_definition)
        flow_definition['nodes'] = nodes
        
        # Persist the updated flow
        if flow_id and session:
            result = set_entire_flow(flow_definition, flow_id, session)
            if "✅" in result:
                return f"Added {node_kind} node '{node_id}'"
            return result
        
        return f"Added {node_kind} node '{node_id}' (not persisted - missing flow_id/session)"
        
    except Exception as e:
        logger.error(f"Failed to add node: {str(e)}")
        return f"Failed to add node: {str(e)}"


def update_node(flow_definition: Dict[str, Any], node_id: str, updates: Dict[str, Any], flow_id: UUID | None = None, session: Session | None = None) -> str:
    """Update an existing node in the flow."""
    try:
        logger.info(f"update_node called: node_id={node_id}, updates={updates}, flow_id={flow_id}, session={'present' if session else 'None'}")
        
        if not updates:
            logger.warning(f"update_node: No updates provided for node '{node_id}'")
            return f"No updates provided for node '{node_id}'"
            
        nodes = flow_definition.get('nodes', [])
        logger.info(f"update_node: Working with flow containing {len(nodes)} nodes")
        
        # Find and log the original node state
        original_node = None
        for node in nodes:
            if node.get('id') == node_id:
                original_node = node.copy()
                break
        
        if original_node:
            logger.info(f"update_node: BEFORE - Node '{node_id}' current state: {original_node}")
        
        node_found = False
        for node in nodes:
            if node.get('id') == node_id:
                logger.info(f"update_node: Applying updates {updates} to node '{node_id}'")
                node.update(updates)
                logger.info(f"update_node: AFTER - Node '{node_id}' new state: {node}")
                node_found = True
                break
        
        if not node_found:
            logger.error(f"update_node: Node '{node_id}' not found in flow")
            return f"Node '{node_id}' not found in flow"
        
        # Persist the updated flow
        if flow_id and session:
            logger.info(f"update_node: Persisting changes via set_entire_flow for flow {flow_id}")
            result = set_entire_flow(flow_definition, flow_id, session)
            logger.info(f"update_node: set_entire_flow returned: {result}")
            
            if "✅" in result:
                success_msg = f"Updated node '{node_id}': {', '.join(updates.keys())}"
                logger.info(f"update_node: SUCCESS - {success_msg}")
                return success_msg
            else:
                logger.error(f"update_node: set_entire_flow failed: {result}")
                return result
        else:
            logger.warning(f"update_node: Not persisting - missing flow_id={flow_id} or session={'present' if session else 'None'}")
            return f"Updated node '{node_id}' (not persisted - missing flow_id/session)"
        
    except Exception as e:
        logger.error(f"Failed to update node '{node_id}': {str(e)}")
        return f"Failed to update node '{node_id}': {str(e)}"


def delete_node(flow_definition: Dict[str, Any], node_id: str, flow_id: UUID | None = None, session: Session | None = None) -> str:
    """Delete a node from the flow."""
    try:
        nodes = flow_definition.get('nodes', [])
        edges = flow_definition.get('edges', [])
        
        # Remove the node
        original_count = len(nodes)
        nodes = [n for n in nodes if n.get('id') != node_id]
        
        if len(nodes) == original_count:
            return f"Node '{node_id}' not found in flow"
        
        # Remove all edges connected to this node
        edges = [e for e in edges if e.get('source') != node_id and e.get('target') != node_id]
        
        flow_definition['nodes'] = nodes
        flow_definition['edges'] = edges
        
        # Persist the updated flow
        if flow_id and session:
            result = set_entire_flow(flow_definition, flow_id, session)
            if "✅" in result:
                return f"Deleted node '{node_id}' and all connected edges"
            return result
            
        return f"Deleted node '{node_id}' (not persisted - missing flow_id/session)"
        
    except Exception as e:
        logger.error(f"Failed to delete node '{node_id}': {str(e)}")
        return f"Failed to delete node '{node_id}': {str(e)}"


def add_edge(flow_definition: Dict[str, Any], source: str, target: str, priority: int = 0, guard: Dict[str, Any] | None = None, condition_description: str | None = None, flow_id: UUID | None = None, session: Session | None = None) -> str:
    """Add a new edge to the flow."""
    try:
        edges = flow_definition.get('edges', [])
        
        # Check if edge already exists
        if any(e.get('source') == source and e.get('target') == target for e in edges):
            return f"Edge from '{source}' to '{target}' already exists"
        
        new_edge = {'source': source, 'target': target, 'priority': priority}
        if guard:
            new_edge['guard'] = guard
        if condition_description:
            new_edge['condition_description'] = condition_description
        
        edges.append(new_edge)
        flow_definition['edges'] = edges
        
        # Persist the updated flow
        if flow_id and session:
            result = set_entire_flow(flow_definition, flow_id, session)
            if "✅" in result:
                return f"Added edge from '{source}' to '{target}'"
            return result
            
        return f"Added edge from '{source}' to '{target}' (not persisted - missing flow_id/session)"
        
    except Exception as e:
        logger.error(f"Failed to add edge from '{source}' to '{target}': {str(e)}")
        return f"Failed to add edge from '{source}' to '{target}': {str(e)}"


def update_edge(flow_definition: Dict[str, Any], source: str, target: str, updates: Dict[str, Any], flow_id: UUID | None = None, session: Session | None = None) -> str:
    """Update an existing edge in the flow."""
    try:
        if not updates:
            return f"No updates provided for edge from '{source}' to '{target}'"
            
        edges = flow_definition.get('edges', [])
        edge_found = False
        
        for edge in edges:
            if edge.get('source') == source and edge.get('target') == target:
                edge.update(updates)
                edge_found = True
                break
        
        if not edge_found:
            return f"Edge from '{source}' to '{target}' not found in flow"
        
        # Persist the updated flow
        if flow_id and session:
            result = set_entire_flow(flow_definition, flow_id, session)
            if "✅" in result:
                return f"Updated edge from '{source}' to '{target}': {', '.join(updates.keys())}"
            return result
            
        return f"Updated edge from '{source}' to '{target}' (not persisted - missing flow_id/session)"
        
    except Exception as e:
        logger.error(f"Failed to update edge from '{source}' to '{target}': {str(e)}")
        return f"Failed to update edge from '{source}' to '{target}': {str(e)}"


def delete_edge(flow_definition: Dict[str, Any], source: str, target: str, flow_id: UUID | None = None, session: Session | None = None) -> str:
    """Delete an edge from the flow."""
    try:
        edges = flow_definition.get('edges', [])
        
        original_count = len(edges)
        edges = [e for e in edges if not (e.get('source') == source and e.get('target') == target)]
        
        if len(edges) == original_count:
            return f"Edge from '{source}' to '{target}' not found in flow"
        
        flow_definition['edges'] = edges
        
        # Persist the updated flow
        if flow_id and session:
            result = set_entire_flow(flow_definition, flow_id, session)
            if "✅" in result:
                return f"Deleted edge from '{source}' to '{target}'"
            return result
            
        return f"Deleted edge from '{source}' to '{target}' (not persisted - missing flow_id/session)"
        
    except Exception as e:
        logger.error(f"Failed to delete edge from '{source}' to '{target}': {str(e)}")
        return f"Failed to delete edge from '{source}' to '{target}': {str(e)}"


def validate_flow(flow_definition: Dict[str, Any]) -> ToolResult:
    """Validate a flow definition without modifying it."""
    try:
        flow_ir = FlowIR.model_validate(flow_definition)
        compiler = FlowCompiler()
        compiled = compiler.compile(flow_ir)
        
        if hasattr(compiled, 'validation_errors') and compiled.validation_errors:
            return ToolResult(
                success=False,
                action="validate_flow",
                message="Flow validation failed:\n" + "\n".join(f"- {error}" for error in compiled.validation_errors),
                is_validation=True
            )
        elif hasattr(compiled, 'errors') and compiled.errors:
            return ToolResult(
                success=False,
                action="validate_flow",
                message="Flow validation failed:\n" + "\n".join(f"- {error}" for error in compiled.errors),
                is_validation=True
            )
        
        if hasattr(compiled, 'validation_warnings') and compiled.validation_warnings:
            warnings = "\n".join(f"- {warning}" for warning in compiled.validation_warnings)
            return ToolResult(
                success=True,
                action="validate_flow",
                message=f"Flow is valid with warnings:\n{warnings}",
                is_validation=True,
                should_continue=False  # Validation after modifications suggests completion
            )
        elif hasattr(compiled, 'warnings') and compiled.warnings:
            warnings = "\n".join(f"- {warning}" for warning in compiled.warnings)
            return ToolResult(
                success=True,
                action="validate_flow",
                message=f"Flow is valid with warnings:\n{warnings}",
                is_validation=True,
                should_continue=False  # Validation after modifications suggests completion
            )
        
        return ToolResult(
            success=True,
            action="validate_flow",
            message="Flow validation passed - no errors or warnings!",
            is_validation=True,
            should_continue=False  # Validation after modifications suggests completion
        )
        
    except Exception as e:
        return ToolResult(
            success=False,
            action="validate_flow",
            message=f"Failed to validate flow: {str(e)}",
            is_validation=True
        )


def get_flow_summary(flow_definition: Dict[str, Any]) -> ToolResult:
    """Get a summary of the current flow structure."""
    try:
        if not flow_definition:
            return ToolResult(
                success=False,
                action="get_flow_summary",
                message="No flow definition loaded",
                is_validation=True
            )
        
        nodes = flow_definition.get('nodes', [])
        edges = flow_definition.get('edges', [])
        entry = flow_definition.get('entry', 'unknown')
        flow_id = flow_definition.get('id', 'unknown')
        
        # Count node types
        node_types = {}
        for node in nodes:
            kind = node.get('kind', 'unknown')
            node_types[kind] = node_types.get(kind, 0) + 1
        
        # Find terminal nodes
        terminals = [n.get('id', 'unknown') for n in nodes if n.get('kind') == 'Terminal']
        
        summary_lines = [
            f"Flow Summary ({flow_id}):",
            f"- Entry point: {entry}",
            f"- Total nodes: {len(nodes)}",
        ]
        
        for kind, count in sorted(node_types.items()):
            summary_lines.append(f"  - {kind}: {count}")
        
        summary_lines.extend([
            f"- Total edges: {len(edges)}",
            f"- Terminals: {', '.join(terminals) if terminals else 'none'}"
        ])
        
        return ToolResult(
            success=True,
            action="get_flow_summary",
            message="\n".join(summary_lines),
            is_validation=True,
            should_continue=False  # Summary after modifications suggests completion
        )
        
    except Exception as e:
        return ToolResult(
            success=False,
            action="get_flow_summary",
            message=f"Failed to get flow summary: {str(e)}",
            is_validation=True
        )


# Tool specifications for the FlowChatAgent
# Note: The agent will automatically inject flow_definition, flow_id, and session
FLOW_MODIFICATION_TOOLS = [
    {
        "name": "set_entire_flow",
        "description": "Replace the entire flow definition. Use this for complete flow creation or major rewrites.",
        "args_schema": SetEntireFlowRequest,
        "func": set_entire_flow
    },
    {
        "name": "add_node", 
        "description": "Add a new node to the flow.",
        "args_schema": AddNodeRequest,
        "func": add_node
    },
    {
        "name": "update_node",
        "description": "Update an existing node in the flow.",
        "args_schema": UpdateNodeRequest, 
        "func": update_node
    },
    {
        "name": "delete_node",
        "description": "Delete a node from the flow.",
        "args_schema": DeleteNodeRequest,
        "func": delete_node
    },
    {
        "name": "add_edge",
        "description": "Add a new edge connecting two nodes.",
        "args_schema": AddEdgeRequest,
        "func": add_edge
    },
    {
        "name": "update_edge",
        "description": "Update an existing edge in the flow.", 
        "args_schema": UpdateEdgeRequest,
        "func": update_edge
    },
    {
        "name": "delete_edge",
        "description": "Delete an edge from the flow.",
        "args_schema": DeleteEdgeRequest,
        "func": delete_edge
    },
    {
        "name": "validate_flow",
        "description": "Validate the current flow definition for errors.",
        "args_schema": ValidateFlowRequest,
        "func": validate_flow
    },
    {
        "name": "get_flow_summary",
        "description": "Get a structural summary of the current flow.",
        "args_schema": GetFlowSummaryRequest,
        "func": get_flow_summary
    }
]
