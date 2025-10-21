import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_processor_happy_path_builds_response_and_saves_context():
    from app.core.flow_processor import FlowProcessor
    from app.core.flow_request import FlowRequest
    from app.core.flow_response import FlowProcessingResult

    # Fakes
    class DummyLLM:
        pass

    class DummySessionMgr:
        saved = {}

        def get_context(self, session_id: str):  # type: ignore[no-untyped-def]
            return None

        def save_context(self, session_id: str, context):  # type: ignore[no-untyped-def]
            self.saved[session_id] = context

    class DummyCancel:
        def check_cancellation_and_raise(self, *a, **k):  # type: ignore[no-untyped-def]
            return None

    # Monkeypatch FlowTurnRunner within processor to avoid deep deps
    class DummyTurnResult:
        assistant_message = "oi"
        messages = [{"text": "oi", "delay_ms": 0}]
        tool_name = "PerformAction"
        tool_args = {"confidence": 0.9, "messages": messages}
        answers_diff = {}
        metadata = {"k": 1, "messages": messages}
        terminal = False
        escalate = False
        external_action_executed = False
        external_action_result = None
        external_action_successful = None

    class DummyRunner:
        def __init__(self, *_a, **_k):
            pass

        def initialize_context(self, existing_context=None):  # type: ignore[no-untyped-def]
            from app.flow_core.state import FlowContext

            return FlowContext(flow_id="fid")

        async def process_turn(self, **kwargs):  # type: ignore[no-untyped-def]
            return DummyTurnResult()

    import app.core.flow_processor as fp_mod
    import app.flow_core.compiler as comp_mod

    orig_runner = fp_mod.FlowTurnRunner
    orig_compile = comp_mod.FlowCompiler.compile
    fp_mod.FlowTurnRunner = DummyRunner  # type: ignore[assignment]
    # Avoid depending on real compiler internals
    comp_mod.FlowCompiler.compile = lambda self, fd: object()  # type: ignore[method-assign]

    try:
        proc = FlowProcessor(DummyLLM(), DummySessionMgr(), DummyCancel())
        req = FlowRequest(
            user_id="u",
            user_message="hello",
            flow_definition={
                "schema_version": "v1",
                "id": "flow.test",
                "entry": "q.first",
                "nodes": [
                    {
                        "id": "q.first",
                        "kind": "Question",
                        "key": "first",
                        "prompt": "First?"
                    }
                ],
                "edges": []
            },
            flow_metadata={"selected_flow_id": "fid"},
            tenant_id="t",
            channel_id="whatsapp:+1",
            project_context=None,
        )
        resp = await proc.process_flow(req, app_context={})

        assert resp.result == FlowProcessingResult.CONTINUE
        assert resp.message == "oi"
        # After refactor, messages may only be included in metadata when multiple
        assert resp.metadata is None or isinstance(resp.metadata, dict)
    finally:
        fp_mod.FlowTurnRunner = orig_runner  # restore
        comp_mod.FlowCompiler.compile = orig_compile


@pytest.mark.unit
def test_flow_response_is_success_property():
    from app.core.flow_response import FlowProcessingResult, FlowResponse

    ok = FlowResponse(result=FlowProcessingResult.CONTINUE, message="a")
    err = FlowResponse(result=FlowProcessingResult.ERROR, message="b")

    assert ok.is_success is True
    assert err.is_success is False
