import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_turn_runner_path_with_existing_tool_result():
    from app.flow_core.runner import FlowTurnRunner
    from app.flow_core.state import FlowContext

    class DummyLLM:
        pass

    # Fake compiled flow is unused by runner logic in our path
    runner = FlowTurnRunner(llm_client=DummyLLM(), compiled_flow={})

    # Monkeypatch responder to simulate existing tool result (avoid double execution)
    class _Output:
        tool_name = "PerformAction"

        class _TR:
            updates = {"field": "v"}
            metadata = {"m": 1}
            terminal = False
            escalate = False
            external_action_executed = False
            external_action_result = None

        tool_result = _TR()
        messages = [{"text": "hi", "delay_ms": 0}]
        confidence = 0.9
        reasoning = "r"

    async def fake_respond(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _Output()

    # Patch internal responder
    runner._responder.respond = fake_respond  # type: ignore[attr-defined]

    ctx = FlowContext(flow_id="f")
    out = await runner.process_turn(
        ctx=ctx, user_message="hello", project_context=None, is_admin=False
    )

    # FlowTurnRunner now returns ToolExecutionResult, not TurnResult
    assert isinstance(out.terminal, bool)
    assert isinstance(out.escalate, bool)
    assert isinstance(out.metadata, dict)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_turn_runner_handles_tool_call_without_existing_result():
    from app.flow_core.runner import FlowTurnRunner
    from app.flow_core.state import FlowContext

    class DummyLLM:
        pass

    runner = FlowTurnRunner(llm_client=DummyLLM(), compiled_flow={})

    class _OutputNoTool:
        tool_name = None
        tool_result = None
        messages = []
        confidence = 0.8
        reasoning = ""

    async def fake_respond(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _OutputNoTool()

    # Let tool_executor path run; create a PerformAction call in llm_response via _process_tool_calls
    runner._responder.respond = fake_respond  # type: ignore[attr-defined]

    # Patch tool executor to return deterministic result
    class _TR:
        updates = {}
        metadata = {}
        terminal = True
        escalate = False
        external_action_executed = False
        external_action_result = None

    async def fake_execute_tool(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _TR()

    runner._tool_executor.execute_tool = fake_execute_tool  # type: ignore[attr-defined]

    ctx = FlowContext(flow_id="f")
    out = await runner.process_turn(
        ctx=ctx, user_message="hi", project_context=None, is_admin=False
    )

    assert isinstance(out.terminal, bool)
    assert isinstance(out.escalate, bool)
    assert isinstance(out.metadata, dict)
