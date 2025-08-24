from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.flow_core.compiler import CompiledFlow as _CompiledFlow
from app.flow_core.compiler import compile_flow
from app.flow_core.ir import (
    ActionNode,
    DecisionNode,
    Flow,
    QuestionNode,
    SubflowNode,
    TerminalNode,
)
from app.db.session import get_db_session
from app.db.repository import get_flow_by_id

router = APIRouter(prefix="/flows", tags=["flows"])


def _playground_flow_path() -> Path:
    # /backend/playground/flow_example.json relative to this file
    # __file__ = backend/app/api/flows.py -> parents[2] = backend
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "playground" / "flow_example.json"


@router.get("/example/raw")
async def get_example_flow_raw() -> dict[str, Any]:
    """Return the raw example flow JSON as-is (legacy v1 will be upgraded by CLI/clients).

    Frontend can render this directly as a graph.
    """
    path = _playground_flow_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Example flow not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[return-value]
    except Exception as exc:  # pragma: no cover - IO/parsing
        raise HTTPException(status_code=500, detail=f"Failed to read example flow: {exc}") from exc


def _sanitize_compiled(compiled: _CompiledFlow) -> dict[str, Any]:
    nodes: dict[str, Any] = {}
    for node_id, node in compiled.nodes.items():
        base: dict[str, Any] = {
            "id": node.id,
            "kind": node.kind,
            "label": getattr(node, "label", None),
            # Common behavior hints useful for the editor/visualizer
            "skippable": getattr(node, "skippable", False),
            "revisitable": getattr(node, "revisitable", True),
            "max_attempts": getattr(node, "max_attempts", 3),
        }

        if isinstance(node, QuestionNode):
            base.update(
                {
                    "key": node.key,
                    "prompt": node.prompt,
                    "validator": node.validator,
                    "clarification": node.clarification,
                    "examples": node.examples,
                    "allowed_values": node.allowed_values,
                    "data_type": node.data_type,
                    "required": node.required,
                    "dependencies": node.dependencies,
                    "priority": node.priority,
                }
            )
        elif isinstance(node, DecisionNode):
            base.update(
                {
                    "decision_type": node.decision_type,
                    "decision_prompt": node.decision_prompt,
                }
            )
        elif isinstance(node, TerminalNode):
            base.update(
                {
                    "reason": node.reason,
                    "success": node.success,
                    "next_flow": node.next_flow,
                    "handoff_required": node.handoff_required,
                }
            )
        elif isinstance(node, ActionNode):
            base.update(
                {
                    "action_type": node.action_type,
                    "action_config": node.action_config,
                    "output_keys": node.output_keys,
                }
            )
        elif isinstance(node, SubflowNode):
            base.update(
                {
                    "flow_ref": node.flow_ref,
                    "input_mapping": node.input_mapping,
                    "output_mapping": node.output_mapping,
                }
            )

        nodes[node_id] = base
    edges_from: dict[str, list[dict[str, Any]]] = {}
    for src, edges in compiled.edges_from.items():
        edges_from[src] = [
            {
                "source": e.source,
                "target": e.target,
                "priority": e.priority,
                "label": e.label,
                "condition_description": e.condition_description,
            }
            for e in edges
        ]
    # Recursively sanitize subflows
    subflows: dict[str, Any] = {}
    for name, sub in compiled.subflows.items():
        subflows[name] = _sanitize_compiled(sub)
    return {
        "id": compiled.id,
        "entry": compiled.entry,
        "nodes": nodes,
        "edges_from": edges_from,
        "metadata": compiled.metadata if compiled.metadata else None,
        "subflows": subflows,
    }


@router.get("/example/compiled")
async def get_example_flow_compiled() -> dict[str, Any]:
    """Return the example flow compiled to v2 CompiledFlow.

    This upgrades schema to v2 in-memory before compile.
    """
    path = _playground_flow_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Example flow not found")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("schema_version") != "v2":
            raw["schema_version"] = "v2"
        flow = Flow.model_validate(raw)
        compiled = compile_flow(flow)
        return _sanitize_compiled(compiled)
    except Exception as exc:  # pragma: no cover - compile failures surfaced as 500
        raise HTTPException(
            status_code=500, detail=f"Failed to compile example flow: {exc}"
        ) from exc


@router.get("/{flow_id}/compiled")
async def get_flow_compiled(
    flow_id: UUID = Path(...), 
    session: Session = Depends(get_db_session)
) -> dict[str, Any]:
    """Return a specific flow compiled to CompiledFlow format."""
    try:
        # Get flow from database
        flow_record = get_flow_by_id(session, flow_id)
        if not flow_record:
            raise HTTPException(status_code=404, detail="Flow not found")
        
        # Get flow definition
        flow_data = flow_record.definition
        if not flow_data:
            raise HTTPException(status_code=404, detail="Flow definition not found")
        
        # Ensure schema version is v2
        if isinstance(flow_data, dict) and flow_data.get("schema_version") != "v2":
            flow_data["schema_version"] = "v2"
        
        # Validate and compile flow
        flow = Flow.model_validate(flow_data)
        compiled = compile_flow(flow)
        return _sanitize_compiled(compiled)
        
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to compile flow: {exc}"
        ) from exc
