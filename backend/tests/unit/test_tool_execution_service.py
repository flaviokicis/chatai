from typing import Any

import pytest


class _FakeContext:
    user_id = "u"
    session_id = "s"
    tenant_id = "t"
    channel_id = "c"
    current_node_id = "n"
    flow_id = "f"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_execution_internal_actions_update_navigate():
    from app.flow_core.actions.registry import ActionRegistry
    from app.flow_core.services.tool_executor import ToolExecutionService

    # Bypass default executor registration to avoid heavy deps
    reg = object.__new__(ActionRegistry)  # type: ignore[call-arg]
    reg._executors = {}  # type: ignore[attr-defined]
    svc = ToolExecutionService(reg)
    ctx = _FakeContext()

    res = await svc.execute_tool(
        tool_name="PerformAction",
        tool_data={
            "actions": ["update", "navigate"],
            "updates": {"email": "a@b.com"},
            "target_node_id": "q.next",
        },
        context=ctx,
        pending_field="email",
    )

    assert res.has_updates is True
    assert res.updates == {"email": "a@b.com"}
    assert res.navigation == {"target_node_id": "q.next"}
    assert res.escalate is False
    assert res.terminal is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_execution_handoff_and_complete_and_restart_metadata():
    from app.flow_core.actions.registry import ActionRegistry
    from app.flow_core.services.tool_executor import ToolExecutionService

    reg = object.__new__(ActionRegistry)  # type: ignore[call-arg]
    reg._executors = {}  # type: ignore[attr-defined]
    svc = ToolExecutionService(reg)
    ctx = _FakeContext()

    res = await svc.execute_tool(
        tool_name="PerformAction",
        tool_data={
            "actions": ["handoff", "complete", "restart"],
            "handoff_reason": "user_requested",
        },
        context=ctx,
        pending_field=None,
    )

    assert res.escalate is True
    assert res.terminal is True
    assert res.metadata.get("handoff_reason") == "user_requested"
    assert res.metadata.get("restart") is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_execution_external_action_success_path():
    from app.flow_core.actions.base import ActionExecutor, ActionResult
    from app.flow_core.actions.registry import ActionRegistry
    from app.flow_core.services.tool_executor import ToolExecutionService

    class DummyExec(ActionExecutor):
        @property
        def action_name(self) -> str:  # type: ignore[override]
            return "modify_flow"

        async def execute(
            self, parameters: dict[str, Any], context: dict[str, Any]
        ) -> ActionResult:  # type: ignore[override]
            # Assert context propagation is correct and flow_id injected
            assert parameters.get("flow_id") == "f"
            assert context["user_id"] == "u"
            return ActionResult(success=True, message="done")

    reg = object.__new__(ActionRegistry)  # type: ignore[call-arg]
    reg._executors = {}  # type: ignore[attr-defined]
    reg.register(DummyExec())
    svc = ToolExecutionService(reg)
    ctx = _FakeContext()

    res = await svc.execute_tool(
        tool_name="PerformAction",
        tool_data={
            "actions": ["modify_flow", "stay"],
            "flow_modification_instruction": "do it",
        },
        context=ctx,
        pending_field=None,
    )

    assert res.external_action_executed is True
    assert res.external_action_result is not None
    assert res.external_action_result.is_success is True
    assert res.requires_llm_feedback is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_execution_external_action_missing_executor_creates_failure_result():
    from app.flow_core.actions.registry import ActionRegistry
    from app.flow_core.services.tool_executor import ToolExecutionService

    reg = object.__new__(ActionRegistry)  # type: ignore[call-arg]
    reg._executors = {}  # type: ignore[attr-defined]
    svc = ToolExecutionService(reg)
    ctx = _FakeContext()

    res = await svc.execute_tool(
        tool_name="PerformAction",
        tool_data={"actions": ["modify_flow"]},
        context=ctx,
        pending_field=None,
    )

    assert res.external_action_executed is True
    assert res.external_action_result is not None
    assert res.external_action_result.is_success is False
    assert res.requires_llm_feedback is True
