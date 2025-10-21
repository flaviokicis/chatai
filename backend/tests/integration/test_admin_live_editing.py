import copy
from uuid import uuid4

import pytest

from app.flow_core.actions.base import ActionResult
from app.flow_core.services.responder import EnhancedFlowResponder
from app.flow_core.state import FlowContext


class StubLLM:
    """Simple LLM stub returning a predefined tool call payload."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def extract(self, instruction, tools):  # type: ignore[no-untyped-def]
        return copy.deepcopy(self._payload)

    def rewrite(self, instruction: str, text: str) -> str:
        return text


class StubActionRegistry:
    """Stubbed action registry that records external action executions."""

    created_instances: list["StubActionRegistry"] = []

    def __init__(self, _llm) -> None:  # type: ignore[no-untyped-def]
        self.calls: list[dict] = []
        self._executors = {
            "modify_flow": self._build_executor("modify_flow"),
            "update_communication_style": self._build_executor("update_communication_style"),
        }
        StubActionRegistry.created_instances.append(self)

    def _build_executor(self, name: str):
        registry = self

        class _Executor:
            action_name = name

            async def execute(self, parameters: dict, context: dict) -> ActionResult:
                registry.calls.append(
                    {
                        "action": name,
                        "parameters": copy.deepcopy(parameters),
                        "context": copy.deepcopy(context),
                    }
                )
                return ActionResult(
                    success=True,
                    message=f"{name} executed",
                    data={"action": name},
                )

        return _Executor()

    def get_executor(self, action_name: str):
        return self._executors.get(action_name)

    def register(self, executor) -> None:  # type: ignore[no-untyped-def]
        self._executors[executor.action_name] = executor

    def has_executor(self, action_name: str) -> bool:
        return action_name in self._executors

    def list_actions(self) -> list[str]:
        return list(self._executors)


@pytest.fixture(autouse=True)
def patch_action_registry(monkeypatch: pytest.MonkeyPatch):
    """Automatically patch the responder to use the stub action registry."""
    StubActionRegistry.created_instances.clear()
    monkeypatch.setattr(
        "app.flow_core.actions.ActionRegistry",
        StubActionRegistry,
    )
    yield


def _build_context(flow_id: str = "flow-basic") -> FlowContext:
    ctx = FlowContext(flow_id=flow_id)
    ctx.current_node_id = "q.start"
    ctx.user_id = "whatsapp:+5511999999999"
    ctx.session_id = "session-123"
    ctx.channel_id = "whatsapp:+5511000000000"
    ctx.tenant_id = uuid4()
    return ctx


@pytest.mark.asyncio
async def test_basic_flow_response_handles_regular_message():
    payload = {
        "tool_calls": [
            {
                "name": "PerformAction",
                "arguments": {
                    "actions": ["stay"],
                    "messages": [{"text": "Olá! Como posso ajudar?", "delay_ms": 0}],
                    "confidence": 0.88,
                    "reasoning": "Respond to greeting",
                },
            }
        ],
        "content": "Olá! Como posso ajudar?",
    }

    responder = EnhancedFlowResponder(StubLLM(payload))
    context = _build_context()

    output = await responder.respond(
        prompt="Como posso ajudar?",
        pending_field="service",
        context=context,
        user_message="Oi",
        project_context=None,
        is_admin=False,
    )

    assert output.tool_name == "PerformAction"
    assert output.messages == [{"text": "Olá! Como posso ajudar?", "delay_ms": 0}]
    assert output.tool_result.external_action_executed is False
    assert output.tool_result.metadata["tool_name"] == "PerformAction"


@pytest.mark.asyncio
async def test_off_topic_question_triggers_clarification():
    payload = {
        "tool_calls": [
            {
                "name": "PerformAction",
                "arguments": {
                    "actions": ["stay"],
                    "messages": [{"text": "Vamos voltar ao fluxo principal, tudo bem?", "delay_ms": 0}],
                    "confidence": 0.75,
                    "reasoning": "Keep user focused on the flow",
                    "clarification_reason": "off_topic",
                },
            }
        ],
        "content": "Vamos voltar ao fluxo principal, tudo bem?",
    }

    responder = EnhancedFlowResponder(StubLLM(payload))
    context = _build_context()

    output = await responder.respond(
        prompt="Alguma dúvida sobre o serviço?",
        pending_field=None,
        context=context,
        user_message="Qual o placar do jogo?",
        project_context=None,
        is_admin=False,
    )

    assert output.tool_name == "PerformAction"
    assert output.messages[0]["text"].startswith("Vamos voltar ao fluxo principal")
    assert output.tool_result.metadata.get("clarification_reason") == "off_topic"
    assert output.tool_result.external_action_executed is False


@pytest.mark.asyncio
async def test_admin_can_request_communication_style_update():
    new_style = "Seja mais carismático, mantenha respostas curtas e use emojis com moderação."
    payload = {
        "tool_calls": [
            {
                "name": "PerformAction",
                "arguments": {
                    "actions": ["update_communication_style", "stay"],
                    "messages": [{"text": "Vou atualizar o estilo para ficar mais carismático, ok?", "delay_ms": 0}],
                    "confidence": 0.92,
                    "reasoning": "Admin requested a communication style change",
                    "updated_communication_style": new_style,
                },
            }
        ],
        "content": "Vou atualizar o estilo para ficar mais carismático, ok?",
    }

    responder = EnhancedFlowResponder(StubLLM(payload))
    context = _build_context(flow_id="flow-style")

    output = await responder.respond(
        prompt="Como devo responder os clientes?",
        pending_field=None,
        context=context,
        user_message="Como admin, quero que use um tom mais carismático.",
        project_context=None,
        is_admin=True,
    )

    registry = StubActionRegistry.created_instances[-1]
    assert len(registry.calls) == 1
    call = registry.calls[0]

    assert call["action"] == "update_communication_style"
    assert call["parameters"]["updated_communication_style"] == new_style
    assert call["context"]["user_id"] == context.user_id
    assert call["context"]["tenant_id"] == context.tenant_id
    assert call["context"]["current_node_id"] == context.current_node_id

    assert output.tool_result.external_action_executed is True
    assert output.tool_result.external_action_result is not None
    assert output.tool_result.external_action_result.success is True
    assert output.tool_result.external_action_result.data == {"action": "update_communication_style"}


@pytest.mark.asyncio
async def test_admin_can_invoke_modify_flow_live_tool():
    instruction = "Divida a pergunta inicial em duas etapas distintas."
    payload = {
        "tool_calls": [
            {
                "name": "PerformAction",
                "arguments": {
                    "actions": ["modify_flow", "stay"],
                    "messages": [{"text": "Posso aplicar essa alteração no fluxo pra você?", "delay_ms": 0}],
                    "confidence": 0.9,
                    "reasoning": "Admin requested live flow edit",
                    "flow_modification_instruction": instruction,
                    "flow_modification_target": "q.start",
                    "flow_modification_type": "prompt",
                },
            }
        ],
        "content": "Posso aplicar essa alteração no fluxo pra você?",
    }

    responder = EnhancedFlowResponder(StubLLM(payload))
    context = _build_context(flow_id="flow-edit")

    output = await responder.respond(
        prompt="Pergunta inicial do fluxo.",
        pending_field="greeting",
        context=context,
        user_message="Como admin, quero dividir essa pergunta em duas.",
        project_context=None,
        is_admin=True,
    )

    registry = StubActionRegistry.created_instances[-1]
    assert len(registry.calls) == 1
    call = registry.calls[0]

    assert call["action"] == "modify_flow"
    assert call["parameters"]["flow_modification_instruction"] == instruction
    assert call["parameters"]["flow_modification_target"] == "q.start"
    assert call["parameters"]["flow_modification_type"] == "prompt"
    assert call["parameters"]["flow_id"] == context.flow_id

    assert call["context"]["user_id"] == context.user_id
    assert call["context"]["tenant_id"] == context.tenant_id
    assert call["context"]["current_node_id"] == context.current_node_id

    assert output.tool_result.external_action_executed is True
    assert output.tool_result.external_action_result is not None
    assert output.tool_result.external_action_result.success is True
    assert output.tool_result.external_action_result.data == {"action": "modify_flow"}
