"""Tools for modifying flow definitions in the flow chat agent."""

from __future__ import annotations

import json
from typing import Any, Dict

from pydantic import BaseModel, Field

from app.flow_core.compiler import FlowCompiler
from app.flow_core.ir import Flow as FlowIR


class SetEntireFlowRequest(BaseModel):
    """Request to replace the entire flow definition."""
    
    flow_definition: Dict[str, Any] = Field(
        description="Complete flow definition JSON that will replace the current flow"
    )


class AddNodeRequest(BaseModel):
    """Request to add a new node to the flow."""
    
    node_definition: Dict[str, Any] = Field(
        description="Complete node definition to add to the flow"
    )
    position_after: str | None = Field(
        default=None, 
        description="ID of the node after which to insert this node (optional)"
    )


class UpdateNodeRequest(BaseModel):
    """Request to update an existing node in the flow."""
    
    node_id: str = Field(description="ID of the node to update")
    updates: Dict[str, Any] = Field(description="Fields to update in the node")


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
    updates: Dict[str, Any] = Field(description="Fields to update in the edge")


class DeleteEdgeRequest(BaseModel):
    """Request to delete an edge from the flow."""
    
    source: str = Field(description="Source node ID of the edge to delete")
    target: str = Field(description="Target node ID of the edge to delete")


def set_entire_flow(flow_definition: Dict[str, Any]) -> str:
    """Replace the entire flow definition with a new one.
    
    This is the primary tool for setting complete flows from scratch,
    especially when users provide WhatsApp conversations or want complete rewrites.
    """
    try:
        # Validate the flow definition
        flow_ir = FlowIR.model_validate(flow_definition)
        compiler = FlowCompiler()
        compiled = compiler.compile(flow_ir)
        
        if hasattr(compiled, 'validation_errors') and compiled.validation_errors:
            return f"Flow validation failed: {'; '.join(compiled.validation_errors)}"
        elif hasattr(compiled, 'errors') and compiled.errors:
            return f"Flow validation failed: {'; '.join(compiled.errors)}"
        
        # Return success message with summary
        node_count = len(flow_definition.get('nodes', []))
        edge_count = len(flow_definition.get('edges', []))
        entry_point = flow_definition.get('entry', 'unknown')
        
        return (
            f"Successfully set complete flow definition:\n"
            f"- Entry point: {entry_point}\n"
            f"- Nodes: {node_count}\n" 
            f"- Edges: {edge_count}\n"
            f"- Flow ID: {flow_definition.get('id', 'unknown')}\n"
            f"Flow is valid and ready to use!"
        )
        
    except Exception as e:
        return f"Failed to set flow definition: {str(e)}"


def add_node(node_definition: Dict[str, Any], position_after: str | None = None) -> str:
    """Add a new node to the flow."""
    try:
        node_id = node_definition.get('id', 'unknown')
        node_kind = node_definition.get('kind', 'unknown')
        
        # Basic validation
        required_fields = ['id', 'kind']
        missing_fields = [f for f in required_fields if f not in node_definition]
        if missing_fields:
            return f"Node missing required fields: {', '.join(missing_fields)}"
        
        position_msg = f" after {position_after}" if position_after else ""
        return f"Added {node_kind} node '{node_id}'{position_msg}"
        
    except Exception as e:
        return f"Failed to add node: {str(e)}"


def update_node(node_id: str, updates: Dict[str, Any]) -> str:
    """Update an existing node in the flow."""
    try:
        updated_fields = list(updates.keys())
        return f"Updated node '{node_id}': {', '.join(updated_fields)}"
        
    except Exception as e:
        return f"Failed to update node '{node_id}': {str(e)}"


def delete_node(node_id: str) -> str:
    """Delete a node from the flow."""
    try:
        return f"Deleted node '{node_id}' and all connected edges"
        
    except Exception as e:
        return f"Failed to delete node '{node_id}': {str(e)}"


def add_edge(source: str, target: str, priority: int = 0, guard: Dict[str, Any] | None = None, condition_description: str | None = None) -> str:
    """Add a new edge to the flow."""
    try:
        guard_msg = f" with guard {guard}" if guard else ""
        condition_msg = f" ({condition_description})" if condition_description else ""
        return f"Added edge from '{source}' to '{target}' (priority {priority}){guard_msg}{condition_msg}"
        
    except Exception as e:
        return f"Failed to add edge from '{source}' to '{target}': {str(e)}"


def update_edge(source: str, target: str, updates: Dict[str, Any]) -> str:
    """Update an existing edge in the flow."""
    try:
        updated_fields = list(updates.keys())
        return f"Updated edge from '{source}' to '{target}': {', '.join(updated_fields)}"
        
    except Exception as e:
        return f"Failed to update edge from '{source}' to '{target}': {str(e)}"


def delete_edge(source: str, target: str) -> str:
    """Delete an edge from the flow."""
    try:
        return f"Deleted edge from '{source}' to '{target}'"
        
    except Exception as e:
        return f"Failed to delete edge from '{source}' to '{target}': {str(e)}"


def validate_flow(flow_definition: Dict[str, Any]) -> str:
    """Validate a flow definition without modifying it."""
    try:
        flow_ir = FlowIR.model_validate(flow_definition)
        compiler = FlowCompiler()
        compiled = compiler.compile(flow_ir)
        
        if hasattr(compiled, 'validation_errors') and compiled.validation_errors:
            return f"Flow validation failed:\n" + "\n".join(f"- {error}" for error in compiled.validation_errors)
        elif hasattr(compiled, 'errors') and compiled.errors:
            return f"Flow validation failed:\n" + "\n".join(f"- {error}" for error in compiled.errors)
        
        if hasattr(compiled, 'validation_warnings') and compiled.validation_warnings:
            warnings = "\n".join(f"- {warning}" for warning in compiled.validation_warnings)
            return f"Flow is valid with warnings:\n{warnings}"
        elif hasattr(compiled, 'warnings') and compiled.warnings:
            warnings = "\n".join(f"- {warning}" for warning in compiled.warnings)
            return f"Flow is valid with warnings:\n{warnings}"
        
        return "Flow validation passed - no errors or warnings!"
        
    except Exception as e:
        return f"Failed to validate flow: {str(e)}"


def get_flow_summary(flow_definition: Dict[str, Any]) -> str:
    """Get a summary of the current flow structure."""
    try:
        if not flow_definition:
            return "No flow definition loaded"
        
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
        
        return "\n".join(summary_lines)
        
    except Exception as e:
        return f"Failed to get flow summary: {str(e)}"


# Tool specifications for the FlowChatAgent
FLOW_MODIFICATION_TOOLS = [
    {
        "name": "set_entire_flow",
        "description": "Replace the entire flow definition. Use this for complete flow creation or major rewrites.",
        "args_schema": SetEntireFlowRequest,
        "func": lambda flow_definition: set_entire_flow(flow_definition)
    },
    {
        "name": "add_node", 
        "description": "Add a new node to the flow.",
        "args_schema": AddNodeRequest,
        "func": lambda node_definition, position_after=None: add_node(node_definition, position_after)
    },
    {
        "name": "update_node",
        "description": "Update an existing node in the flow.",
        "args_schema": UpdateNodeRequest, 
        "func": lambda node_id, updates: update_node(node_id, updates)
    },
    {
        "name": "delete_node",
        "description": "Delete a node from the flow.",
        "args_schema": DeleteNodeRequest,
        "func": lambda node_id: delete_node(node_id)
    },
    {
        "name": "add_edge",
        "description": "Add a new edge connecting two nodes.",
        "args_schema": AddEdgeRequest,
        "func": lambda source, target, priority=0, guard=None, condition_description=None: add_edge(source, target, priority, guard, condition_description)
    },
    {
        "name": "update_edge",
        "description": "Update an existing edge in the flow.", 
        "args_schema": UpdateEdgeRequest,
        "func": lambda source, target, updates: update_edge(source, target, updates)
    },
    {
        "name": "delete_edge",
        "description": "Delete an edge from the flow.",
        "args_schema": DeleteEdgeRequest,
        "func": lambda source, target: delete_edge(source, target)
    },
    {
        "name": "validate_flow",
        "description": "Validate the current flow definition for errors.",
        "args_schema": SetEntireFlowRequest,
        "func": lambda flow_definition: validate_flow(flow_definition)
    },
    {
        "name": "get_flow_summary",
        "description": "Get a structural summary of the current flow.",
        "args_schema": SetEntireFlowRequest,
        "func": lambda flow_definition: get_flow_summary(flow_definition)
    }
]
