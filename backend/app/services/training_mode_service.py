"""Training mode service for handling admin flow training sessions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.db.models import ChatThread, Flow

from app.agents.flow_chat_agent import FlowChatAgent, ToolSpec
from app.agents.flow_modification_tools import FLOW_MODIFICATION_TOOLS
from app.core.state import RedisStore
from app.core.thought_tracer import ThoughtTracer
from app.db.repository import get_flow_by_id
from app.flow_core.compiler import compile_flow
from app.flow_core.ir import Flow as FlowIR
from app.flow_core.runner import FlowTurnRunner
from app.services.flow_chat_service import FlowChatService


class TrainingModeService:
    """Encapsulates training mode logic: handshake, password validation,
    read-only simulation, and flow-edit chat delegation.
    """

    def __init__(self, session: Session, app_context: Any) -> None:  # type: ignore[type-arg]
        self.session = session
        self.app_context = app_context

    # --- Handshake & trigger ---
    @staticmethod
    def _norm(text: str) -> str:
        return (text or "").strip().lower()

    def is_trigger(self, text: str) -> bool:
        t = self._norm(text)
        return t in {"começar treino", "comecar treino", "ativar modo treino"}

    def start_handshake(self, thread: ChatThread, flow: Flow, *, user_id: str, flow_session_key: str) -> str:  # type: ignore[type-arg]
        extra = thread.extra or {}
        extra["awaiting_training_password"] = True
        extra["pending_training_flow_id"] = str(flow.id)
        # Align attempt counter naming
        extra["pendingTrainingModePasswordIndex"] = 0
        thread.extra = extra
        self.session.commit()
        # Initialize pending attempts and mark awaiting in Redis store
        try:
            store = getattr(self.app_context, "store", None)
            if store:
                state = {
                    "awaiting_password": True,
                    "pending_training_flow_id": str(flow.id),
                    "pendingTrainingModePasswordIndex": 0,
                    "flow_session_key": flow_session_key,
                }
                store.save(user_id, "training_mode", state)
        except Exception:
            pass
        return "Para entrar no modo treino, informe a senha."

    def awaiting_password(self, thread: ChatThread, *, user_id: str) -> bool:  # type: ignore[type-arg]
        extra = thread.extra or {}
        if extra.get("awaiting_training_password"):
            return True
        try:
            store = getattr(self.app_context, "store", None)
            if store:
                state = store.load(user_id, "training_mode") or {}
                if isinstance(state, dict):
                    return bool(state.get("awaiting_password", False))
        except Exception:
            return False
        return False

    def validate_password(
        self,
        thread: ChatThread,  # type: ignore[type-arg]
        selected_flow: Flow,  # type: ignore[type-arg]
        message_text: str,
        *,
        user_id: str,
        flow_session_key: str,
    ) -> tuple[bool, str]:
        extra = thread.extra or {}
        flow_id_str = extra.get("pending_training_flow_id")
        target_flow = selected_flow
        if flow_id_str:
            try:
                from uuid import UUID
                target_flow_id = UUID(flow_id_str)
                if target_flow_id != selected_flow.id:
                    tf = get_flow_by_id(self.session, target_flow_id)
                    if tf is not None:
                        target_flow = tf
            except Exception:
                pass

        # Normalize to digits only for validation attempts tracking
        numeric = message_text.strip()
        expected = getattr(target_flow, "training_password", None) or "1234"
        if numeric.isdigit() and self._norm(numeric) == self._norm(str(expected)):
            thread.training_mode = True
            thread.training_mode_since = datetime.now(UTC)
            thread.training_flow_id = target_flow.id
            extra.pop("awaiting_training_password", None)
            extra.pop("pending_training_flow_id", None)
            extra.pop("pendingTrainingModePasswordIndex", None)
            thread.extra = extra
            self.session.commit()
            # Clear Redis pending state
            try:
                store = getattr(self.app_context, "store", None)
                if store:
                    store.save(user_id, "training_mode", {"awaiting_password": False})
            except Exception:
                pass
            return True, "Modo treino ativado. Você pode enviar instruções para editar o fluxo."
        # Handle invalid inputs and attempt counting
        max_attempts = 3
        attempts = int(extra.get("pendingTrainingModePasswordIndex", 0))
        if not numeric.isdigit():
            # Reset conversation and suggest restart
            self._reset_conversation_context(user_id, flow_session_key)
            extra.pop("awaiting_training_password", None)
            extra.pop("pending_training_flow_id", None)
            extra.pop("pendingTrainingModePasswordIndex", None)
            thread.extra = extra
            self.session.commit()
            return True, "Que tal começarmos de novo?"

        # Wrong numeric password
        attempts += 1
        extra["pendingTrainingModePasswordIndex"] = attempts
        thread.extra = extra
        self.session.commit()
        if attempts >= max_attempts:
            # Reset conversation after 3 attempts
            self._reset_conversation_context(user_id, flow_session_key)
            extra.pop("awaiting_training_password", None)
            extra.pop("pending_training_flow_id", None)
            extra.pop("pendingTrainingModePasswordIndex", None)
            thread.extra = extra
            self.session.commit()
            return True, "Que tal começarmos de novo?"
        return True, "Senha incorreta. Tente novamente."

    def _reset_conversation_context(self, user_id: str, flow_session_key: str) -> None:
        """Reset Redis conversation context to avoid interference with next convos."""
        try:
            store = getattr(self.app_context, "store", None)
            if store:
                store.save(user_id, flow_session_key, {})
                store.save(user_id, "training_mode", {})
        except Exception:
            return

    # --- Training mode behaviors ---
    def _build_runner(self, flow_definition: dict[str, Any]) -> FlowTurnRunner:
        if isinstance(flow_definition, dict) and flow_definition.get("schema_version") != "v2":
            flow_definition["schema_version"] = "v2"
        flow_ir = FlowIR.model_validate(flow_definition)
        compiled = compile_flow(flow_ir)
        thought_tracer = None
        if isinstance(self.app_context.store, RedisStore):
            thought_tracer = ThoughtTracer(self.app_context.store)
        return FlowTurnRunner(
            compiled_flow=compiled,
            llm=self.app_context.llm,
            strict_mode=True,
            thought_tracer=thought_tracer,
        )

    def simulate_reply(
        self,
        thread: ChatThread,  # type: ignore[type-arg]
        selected_flow: Flow,  # type: ignore[type-arg]
        message_text: str,
        project_context: Any,  # type: ignore[type-arg]
    ) -> str:
        training_flow_id = thread.training_flow_id or selected_flow.id
        target_flow = selected_flow
        if training_flow_id != selected_flow.id:
            tf = get_flow_by_id(self.session, training_flow_id)
            if tf is not None:
                target_flow = tf

        runner = self._build_runner(dict(target_flow.definition))
        ctx = runner.initialize_context()
        result = runner.process_turn(ctx, user_message=message_text, project_context=project_context)
        return result.assistant_message or ""

    async def handle_training_message(
        self,
        thread: ChatThread,  # type: ignore[type-arg]
        selected_flow: Flow,  # type: ignore[type-arg]
        message_text: str,
        project_context: Any,  # type: ignore[type-arg]
    ) -> str:
        # Simulation triggers (Portuguese and English)
        sim_triggers = ("simular:", "simulate:", "teste:", "test:")
        if any(self._norm(message_text).startswith(t) for t in sim_triggers):
            hypothetical = message_text.split(":", 1)[1].strip() if ":" in message_text else message_text
            return self.simulate_reply(thread, selected_flow, hypothetical, project_context)

        # Flow editing chat behavior using existing tools
        tools = [
            ToolSpec(
                name=t["name"],
                description=t.get("description"),
                args_schema=t.get("args_schema"),
                func=t["func"],
            )
            for t in FLOW_MODIFICATION_TOOLS
        ]
        agent = FlowChatAgent(llm=self.app_context.llm, tools=tools)

        service = FlowChatService(self.session, agent=agent)
        training_flow_id = thread.training_flow_id or selected_flow.id
        response = await service.send_user_message(training_flow_id, message_text)
        return response.messages[-1].content if response and response.messages else ""