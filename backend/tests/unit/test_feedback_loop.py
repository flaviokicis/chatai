import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_feedback_loop_truthful_response_success_path():
    from app.flow_core.actions.base import ActionResult
    from app.flow_core.feedback.loop import FeedbackLoop
    from app.flow_core.state import FlowContext

    class DummyResponder:
        async def respond(self, **kwargs):  # type: ignore[no-untyped-def]
            # Simulate a responder that returns messages aligned with success
            class _Output:
                tool_name = "PerformAction"
                tool_result = type("_TR", (), {"metadata": {}})()
                messages = [{"text": "✅ modificado com sucesso", "delay_ms": 0}]
                confidence = 0.9
                reasoning = "ok"

            return _Output()

    loop = FeedbackLoop(responder=DummyResponder())
    ctx = FlowContext(flow_id="f")
    result = ActionResult(success=True, message="done")

    out = await loop.process_action_result(
        action_name="modify_flow",
        action_result=result,
        context=ctx,
        original_messages=[{"text": "draft", "delay_ms": 0}],
        original_instruction="instr",
    )

    assert out["truthful"] is True
    assert out["messages"] and "sucesso" in out["messages"][0]["text"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_feedback_loop_fallback_on_misaligned_message():
    from app.flow_core.actions.base import ActionResult
    from app.flow_core.feedback.loop import FeedbackLoop
    from app.flow_core.state import FlowContext

    class DummyResponder:
        async def respond(self, **kwargs):  # type: ignore[no-untyped-def]
            class _Output:
                tool_name = "PerformAction"
                tool_result = type("_TR", (), {"metadata": {}})()
                # Message does not acknowledge failure
                messages = [{"text": "Tudo certo!", "delay_ms": 0}]
                confidence = 0.9
                reasoning = "ok"

            return _Output()

    loop = FeedbackLoop(responder=DummyResponder())
    ctx = FlowContext(flow_id="f")
    result = ActionResult(success=False, message="falhou", error="x")

    out = await loop.process_action_result(
        action_name="modify_flow",
        action_result=result,
        context=ctx,
    )

    # Should fallback to truthful error message
    assert out["truthful"] is True
    assert (
        "falhou" in out["messages"][0]["text"].lower()
        or "erro" in out["messages"][0]["text"].lower()
    )
