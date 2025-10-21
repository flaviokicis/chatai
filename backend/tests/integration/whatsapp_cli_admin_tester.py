#!/usr/bin/env python3
"""
Integration harness for exercising the WhatsApp CLI with an autonomous GPT-5 tester.

This script wires the production WhatsApp simulator to a GPT-5 agent that acts as an
admin tester. The tester converses naturally for a few turns and then requests an
administrative change (communication style or flow update), validating that the
change is executed by inspecting metadata and persisted state.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain.schema import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.flow_response import FlowProcessingResult
from app.db.repository import get_tenant_by_id
from app.db.session import db_session
from app.flow_core.whatsapp_cli import WhatsAppSimulatorCLI
from app.services.admin_phone_service import AdminPhoneService

# ---------------------------------------------------------------------------
# Tester configuration (edit these constants to define the tester behaviour)
# ---------------------------------------------------------------------------

DEFAULT_TESTER_OBJECTIVE = {
    "tipo": "communication_style",  # Options: "communication_style" | "flow"
    "descricao": (
        "Use mais emojis."
    ),
}

DEFAULT_STEPS_BEFORE_REQUEST = 2  # Quantos turnos o tester conversa normalmente antes do pedido
DEFAULT_MAX_ROUNDS = 6  # Limite duro para evitar loops infinitos

# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """\
Você é o GPT-5 Tester, um avaliador automático que conversa com o fluxo do WhatsApp CLI.
Objetivo principal: {objective}
Tipo de objetivo: {goal_type}

Regras fixas:
1. Responda sempre em português brasileiro, como um humano real.
2. Mantenha cordialidade profissional e não mencione que é um teste ou que você é um modelo.
3. Você é um administrador legítimo e pode autorizar mudanças quando perguntado.
4. Siga as orientações adicionais recebidas a cada turno antes de responder.
"""

HUMAN_PROMPT_TEMPLATE = """\
Histórico da conversa (mensagens mais antigas primeiro):
{transcript}

Últimas mensagens recebidas do bot:
{latest_messages}

Dados do momento:
- Turno atual (mensagens já enviadas pelo tester após responder): {turn}
- Turnos normais obrigatórios antes do pedido administrativo: {steps}
- Já enviou solicitação administrativa? {admin_request}

Instruções:
1. Se o bot ainda não falou, inicie com uma saudação calorosa e contextualize o assunto.
2. Enquanto não tiver cumprido os {steps} turnos obrigatórios e ainda não tiver feito o pedido administrativo,
   responda como um cliente genuíno, fornecendo detalhes úteis e avançando na conversa.
3. Assim que cumprir os {steps} turnos obrigatórios e ainda não tiver enviado a solicitação administrativa,
   faça agora uma solicitação direta alinhada ao objetivo: {objective}. Deixe claro que você é administrador e
   esteja pronto para confirmar a alteração.
4. Após enviar o pedido administrativo, continue ajudando até que o bot confirme o que foi solicitado.

Responda com APENAS a mensagem que você enviaria ao bot neste momento."""


@dataclass(slots=True)
class TesterObjective:
    """Represents the goal that guides the autonomous tester."""

    tipo: str
    descricao: str


@dataclass(slots=True)
class ConversationRecord:
    """Stores a single conversation message."""

    author: str  # "tester" | "bot"
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class GPT5Tester:
    """LLM agent that generates tester messages given the conversation context."""

    def __init__(
        self,
        objective: TesterObjective,
        steps_before_request: int,
        *,
        model_name: str = "gpt-5",
        temperature: float = 0.4,
    ) -> None:
        self._objective = objective
        self._steps_before_request = max(0, steps_before_request)
        self._model = ChatOpenAI(model=model_name, temperature=temperature)
        self._system_message = SystemMessage(
            content=SYSTEM_PROMPT_TEMPLATE.format(
                objective=objective.descricao,
                goal_type=objective.tipo,
            )
        )
        self._transcript: list[ConversationRecord] = []
        self._turn_count = 0
        self._admin_request_sent = False

    async def next_message(self, bot_messages: Sequence[str]) -> str:
        """Generate the tester's next message given the latest bot outputs."""
        if bot_messages:
            for text in bot_messages:
                self._transcript.append(ConversationRecord(author="bot", text=text))

        turn_index = self._turn_count + 1
        should_request_admin_change = (
            not self._admin_request_sent and turn_index > self._steps_before_request
        )

        human_prompt = HUMAN_PROMPT_TEMPLATE.format(
            transcript=self._format_transcript(),
            latest_messages=self._format_latest(bot_messages),
            turn=turn_index,
            steps=self._steps_before_request,
            admin_request="sim" if self._admin_request_sent else "não",
            objective=self._objective.descricao,
        )

        response = await self._model.ainvoke(
            [self._system_message, HumanMessage(content=human_prompt)]
        )
        reply_text = self._extract_text(response.content)

        self._transcript.append(ConversationRecord(author="tester", text=reply_text))
        self._turn_count = turn_index
        if should_request_admin_change:
            self._admin_request_sent = True

        return reply_text

    def _format_transcript(self) -> str:
        if not self._transcript:
            return "(sem mensagens anteriores; você deve iniciar a conversa)"
        return "\n".join(
            f"{'BOT' if record.author == 'bot' else 'TESTER'}: {record.text}"
            for record in self._transcript
        )

    @staticmethod
    def _format_latest(messages: Sequence[str]) -> str:
        if not messages:
            return "Nenhuma mensagem recebida ainda."
        return "\n".join(f"- {text}" for text in messages)

    @staticmethod
    def _extract_text(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, Iterable):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                else:
                    parts.append(str(item))
            return " ".join(parts).strip()
        return str(content).strip()


class WhatsAppCLIGoalTester:
    """Coordinates the simulator and the GPT-5 tester to perform an integration exercise."""

    def __init__(
        self,
        flow_path: Path,
        tester_objective: TesterObjective,
        *,
        admin_phone: str,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        steps_before_request: int = DEFAULT_STEPS_BEFORE_REQUEST,
        reset_environment: bool = False,
        show_output: bool = True,
    ) -> None:
        if not flow_path.exists():
            raise FileNotFoundError(f"Flow file not found: {flow_path}")

        self._flow_path = flow_path
        self._objective = tester_objective
        self._max_rounds = max_rounds
        self._show_output = show_output
        self._simulator = WhatsAppSimulatorCLI(
            phone_number=None,
            flow_path=str(flow_path),
            model="gpt-5",
            reset=reset_environment,
            user_phone=admin_phone,
        )
        self._tester = GPT5Tester(
            tester_objective,
            steps_before_request,
        )
        self._conversation: list[ConversationRecord] = []
        self._tool_events: list[dict[str, Any]] = []
        self._errors: list[str] = []

    async def setup(self) -> None:
        """Prepare database records and shared services for the simulator."""
        config = None
        if not self._simulator.phone_number:
            config = self._simulator._load_or_create_config()

        self._simulator.conversation_ctx = await self._simulator._setup_database(config)
        if not self._simulator.conversation_ctx:
            raise RuntimeError("Failed to set up conversation context for WhatsApp simulator.")

        services_ready = await self._simulator._initialize_services()
        if not services_ready:
            raise RuntimeError("Failed to initialize WhatsApp simulator services.")

        self._ensure_admin_phone()
        if self._show_output:
            print(f"✅ Ambiente pronto. Tenant: {self._simulator.conversation_ctx.tenant_id}")

    async def execute(self) -> dict[str, Any]:
        """Run the scripted conversation and return execution details."""
        initial_style = (
            self._fetch_current_communication_style()
            if self._objective.tipo == "communication_style"
            else None
        )

        pending_bot_messages: list[str] = []

        for round_index in range(1, self._max_rounds + 1):
            tester_message = await self._tester.next_message(pending_bot_messages)
            self._conversation.append(ConversationRecord(author="tester", text=tester_message))
            if self._show_output:
                print(f"\n👤 Tester (round {round_index}): {tester_message}")

            result = await self._simulator.process_message(
                tester_message,
                capture=True,
                suppress_output=not self._show_output,
            )

            if not result:
                self._errors.append("Simulator returned no response data.")
                break

            if error := result.get("error"):
                self._errors.append(error)
                if self._show_output:
                    print(f"❌ Erro ao processar mensagem: {error}")
                break

            metadata = result.get("metadata", {}) or {}
            tool_name = metadata.get("tool_name")
            if tool_name:
                tool_event = {
                    "round": round_index,
                    "tool_name": tool_name,
                    "metadata": metadata,
                }
                # For PerformAction, capture the actions list
                if tool_name == "PerformAction" and "actions" in result:
                    tool_event["actions"] = result.get("actions", [])
                self._tool_events.append(tool_event)

            bot_messages = [
                msg.get("text", "")
                for msg in result.get("messages", [])
                if isinstance(msg, dict) and msg.get("text")
            ]
            if bot_messages:
                for text in bot_messages:
                    self._conversation.append(ConversationRecord(author="bot", text=text))
                    if self._show_output:
                        print(f"🤖 Bot: {text}")

            pending_bot_messages = bot_messages

            flow_result = result.get("result")
            if flow_result in {FlowProcessingResult.TERMINAL, FlowProcessingResult.ESCALATE}:
                if self._show_output:
                    print(f"\nℹ️ Encerrando conversa (estado: {flow_result.value}).")
                break

        final_style = (
            self._fetch_current_communication_style()
            if self._objective.tipo == "communication_style"
            else None
        )

        style_changed = None
        if initial_style is not None:
            style_changed = (initial_style or "").strip() != (final_style or "").strip()

        expected_action = (
            "update_communication_style" if self._objective.tipo == "communication_style" else "modify_flow"
        )
        # Check if the expected action was executed (it's an action within PerformAction tool)
        tool_observed = any(
            expected_action in event.get("actions", [])
            for event in self._tool_events
        )

        return {
            "objective": self._objective,
            "conversation": [record.__dict__ for record in self._conversation],
            "initial_style": initial_style,
            "final_style": final_style,
            "style_changed": style_changed,
            "tool_events": self._tool_events,
            "expected_tool_detected": tool_observed,
            "errors": self._errors,
            "tenant_id": str(self._simulator.conversation_ctx.tenant_id),
            "admin_phone": self._simulator.user_phone,
        }

    def _ensure_admin_phone(self) -> None:
        """Guarantee that the tester phone number has admin privileges."""
        with db_session() as session:
            admin_service = AdminPhoneService(session)
            admin_service.add_admin_phone(self._simulator.user_phone, self._simulator.conversation_ctx.tenant_id)

    def _fetch_current_communication_style(self) -> str | None:
        """Read the persisted communication style for the active tenant."""
        with db_session() as session:
            tenant = get_tenant_by_id(session, self._simulator.conversation_ctx.tenant_id)
            if tenant and tenant.project_config:
                return tenant.project_config.communication_style
        return None


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute an autonomous GPT-5 integration test against the WhatsApp CLI.",
    )
    parser.add_argument(
        "--flow",
        type=Path,
        default=Path("playground/flow_example.json"),
        help="Caminho para o arquivo de fluxo a ser usado na simulação.",
    )
    parser.add_argument(
        "--admin-phone",
        type=str,
        default="+5511999999999",
        help="Telefone que o tester usará (será marcado como admin automaticamente).",
    )
    parser.add_argument(
        "--goal-type",
        type=str,
        default=DEFAULT_TESTER_OBJECTIVE["tipo"],
        choices=["communication_style", "flow"],
        help="Tipo de objetivo que o tester deve perseguir.",
    )
    parser.add_argument(
        "--goal-description",
        type=str,
        default=DEFAULT_TESTER_OBJECTIVE["descricao"],
        help="Descrição em português do objetivo específico do tester.",
    )
    parser.add_argument(
        "--steps-before-request",
        type=int,
        default=DEFAULT_STEPS_BEFORE_REQUEST,
        help="Quantidade de turnos normais antes do pedido administrativo.",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=DEFAULT_MAX_ROUNDS,
        help="Limite máximo de rodadas de conversa.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Força a criação de um novo ambiente de teste (ignora .whatsapp_cli_config.json).",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Executa em modo silencioso (não imprime a conversa).",
    )
    args = parser.parse_args()

    load_dotenv()

    tester_objective = TesterObjective(tipo=args.goal_type, descricao=args.goal_description)
    runner = WhatsAppCLIGoalTester(
        args.flow,
        tester_objective,
        admin_phone=args.admin_phone,
        max_rounds=args.max_rounds,
        steps_before_request=args.steps_before_request,
        reset_environment=args.reset,
        show_output=not args.no_output,
    )

    await runner.setup()
    result = await runner.execute()

    print("\n" + "=" * 80)
    print("📊 Resumo do teste automatizado")
    print("=" * 80)
    print(f"Objetivo: {result['objective'].tipo} – {result['objective'].descricao}")
    print(f"Telefone admin: {result['admin_phone']}")
    print(f"Tenant ID: {result['tenant_id']}")
    if result["initial_style"] is not None:
        print(f"Estilo inicial:\n{result['initial_style'] or '(não definido)'}")
        print(f"Estilo final:\n{result['final_style'] or '(não definido)'}")
        print(f"Alteração detectada? {'sim' if result['style_changed'] else 'não'}")
    print(f"Ferramenta esperada acionada? {'sim' if result['expected_tool_detected'] else 'não'}")
    if result["errors"]:
        print("Erros encontrados:")
        for err in result["errors"]:
            print(f" - {err}")
    else:
        print("Erros encontrados: nenhum")
    print("=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Execução interrompida pelo usuário.")
