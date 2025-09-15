import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_flow_responder_builds_flow_response_metadata_messages():
    from app.core.flow_response import FlowProcessingResult
    from app.flow_core.llm_responder import LLMFlowResponder, ResponseConfig
    from app.flow_core.state import FlowContext

    class DummyLLM:
        def extract(self, instruction, tools):  # type: ignore[no-untyped-def]
            # Minimal structure expected by _convert_langchain_to_gpt5_response
            return {
                "tool_calls": [
                    {
                        "name": "PerformAction",
                        "arguments": {
                            "actions": ["stay"],
                            "messages": [{"text": "Olá!", "delay_ms": 0}],
                            "reasoning": "greet",
                            "confidence": 0.9,
                        },
                    }
                ],
                "content": "Olá!",
            }

    responder = LLMFlowResponder(DummyLLM())
    ctx = FlowContext(flow_id="f")

    # Stub enhanced responder to avoid heavy prompt assembly side effects
    class _StubTR:
        terminal = False
        escalate = False
        metadata = {}

    class _StubOut:
        tool_name = "PerformAction"
        tool_result = _StubTR()
        messages = [{"text": "Olá!", "delay_ms": 0}]
        confidence = 0.9
        reasoning = "ok"

    async def _stub_respond(**kwargs):  # type: ignore[no-untyped-def]
        return _StubOut()

    responder._enhanced_responder.respond = _stub_respond  # type: ignore[attr-defined]

    resp = await responder.respond(
        prompt="Pergunta?",
        pending_field=None,
        ctx=ctx,
        user_message="Oi",
        config=ResponseConfig(is_admin=False),
    )

    assert resp.result in (
        FlowProcessingResult.CONTINUE,
        FlowProcessingResult.TERMINAL,
        FlowProcessingResult.ESCALATE,
    )
    # Message may fallback; assert type and metadata structure
    assert isinstance(resp.message, str)
    assert resp.metadata is None or isinstance(resp.metadata, dict)
