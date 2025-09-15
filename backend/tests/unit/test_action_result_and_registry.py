from typing import Any

import pytest


@pytest.mark.unit
def test_action_result_semantics_success():
    from app.flow_core.actions.base import ActionResult

    result = ActionResult(success=True, message="ok", data={"k": 1})

    assert result.is_success is True
    assert result.is_failure is False
    assert result.message == "ok"
    assert result.data == {"k": 1}


@pytest.mark.unit
def test_action_result_semantics_failure_with_error():
    from app.flow_core.actions.base import ActionResult

    result = ActionResult(success=False, message="boom", error="trace")

    assert result.is_success is False
    assert result.is_failure is True
    assert result.error == "trace"


@pytest.mark.unit
def test_action_registry_register_and_get_executor():
    from app.flow_core.actions.base import ActionExecutor, ActionResult
    from app.flow_core.actions.registry import ActionRegistry

    class DummyLLM:
        pass

    class DummyExec(ActionExecutor):
        @property
        def action_name(self) -> str:  # type: ignore[override]
            return "dummy_action"

        async def execute(
            self, parameters: dict[str, Any], context: dict[str, Any]
        ) -> ActionResult:  # type: ignore[override]
            return ActionResult(success=True, message="done")

    # Avoid importing default executors; construct empty registry by bypassing __init__
    reg = object.__new__(ActionRegistry)  # type: ignore[call-arg]
    reg._executors = {}  # type: ignore[attr-defined]

    reg.register(DummyExec())
    exec_obj = reg.get_executor("dummy_action")
    assert exec_obj is not None
    assert exec_obj.action_name == "dummy_action"


@pytest.mark.unit
def test_action_registry_rejects_duplicate_registration():
    from app.flow_core.actions.base import ActionExecutor, ActionResult
    from app.flow_core.actions.registry import ActionRegistry

    class DummyLLM:
        pass

    class DummyExec(ActionExecutor):
        @property
        def action_name(self) -> str:  # type: ignore[override]
            return "dup"

        async def execute(
            self, parameters: dict[str, Any], context: dict[str, Any]
        ) -> ActionResult:  # type: ignore[override]
            return ActionResult(success=True, message="ok")

    reg = object.__new__(ActionRegistry)  # type: ignore[call-arg]
    reg._executors = {}  # type: ignore[attr-defined]
    reg.register(DummyExec())
    with pytest.raises(ValueError):
        reg.register(DummyExec())
