from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.agents.base import FlowAgent
from app.core.messages import AgentResult, OutboundMessage
from app.core.tool_schemas import SelectPath
from app.flow_core.engine import Engine
from app.flow_core.responders import LLMResponder, ResponderContext

if TYPE_CHECKING:  # import only for typing
    from app.agents.base import BaseAgentDeps


class SalesQualifierAgent(FlowAgent):
    agent_type = "sales_qualifier"

    @dataclass(slots=True)
    class SalesPathConfig:
        graphs: dict[str, Any] | None = None

    def __init__(
        self,
        user_id: str,
        deps: BaseAgentDeps,
        compiled_flow: object,
        path_compiled: dict[str, object] | None = None,
    ) -> None:
        super().__init__(
            user_id, deps, compiled_flow=compiled_flow, responder=LLMResponder(deps.llm)
        )
        self._path_compiled = path_compiled or {}
        # Note: path selection handled below per-message using SelectPath

    def handle(self, message):  # type: ignore[no-untyped-def]
        # Load state
        stored = self.deps.store.load(self.user_id, self.agent_type) or {}
        answers = dict(stored.get("answers", {}))
        active_path = stored.get("active_path")
        path_locked = bool(stored.get("path_locked", False))

        # Attempt path selection based on existing answers (pre-update)
        if not path_locked and self._path_compiled and (answers.get("intention") not in (None, "")):
            paths = list(self._path_compiled.keys())
            if paths:
                # Ask LLM to pick a path conservatively
                summary = {k: answers.get(k) for k in answers}
                prompt = (
                    "You decide which conversation path to follow based on the user's latest message and known answers.\n"
                    "Be conservative. Choose a path ONLY if the message clearly indicates it. If uncertain, return null.\n\n"
                    f"Latest user message: {message.text or ''}\n"
                    f"Known answers: {summary}\n"
                    f"Available paths: {paths}\n"
                    "Respond by calling SelectPath with 'path' as one of the available paths or null."
                )
                args = self.deps.llm.extract(prompt, [SelectPath])
                chosen = args.get("path") if isinstance(args, dict) else None
                if isinstance(chosen, str) and chosen in paths:
                    active_path = chosen
                    path_locked = True

        # Choose compiled flow (combined) for this turn
        compiled = self._path_compiled.get(active_path) if active_path else self._compiled
        engine = Engine(compiled)
        state = engine.start()
        state.answers.update(answers)

        # 1) Emit current prompt
        out = engine.step(state)
        if out.kind == "terminal":
            return self._escalate("checklist_complete", {"answers": state.answers})

        # 2) Let responder extract updates
        ctx = ResponderContext()
        r = self._responder.respond(
            out.message or "", state.pending_field, state.answers, message.text or "", ctx
        )

        # 3) Apply updates and advance the engine
        for k, v in r.updates.items():
            state.answers[k] = v
        follow = out
        if state.pending_field and state.pending_field in r.updates:
            follow = engine.step(
                state, {"answer": r.updates[state.pending_field], "tool_name": r.tool_name}
            )

        # Re-evaluate path selection after applying updates so the next prompt can come from the path
        if (
            not path_locked
            and self._path_compiled
            and (state.answers.get("intention") not in (None, ""))
        ):
            paths = list(self._path_compiled.keys())
            if paths:
                summary = {k: state.answers.get(k) for k in state.answers}
                prompt = (
                    "You decide which conversation path to follow based on the user's latest message and known answers.\n"
                    "Be conservative. Choose a path ONLY if the message clearly indicates it. If uncertain, return null.\n\n"
                    f"Latest user message: {message.text or ''}\n"
                    f"Known answers: {summary}\n"
                    f"Available paths: {paths}\n"
                    "Respond by calling SelectPath with 'path' as one of the available paths or null."
                )
                args = self.deps.llm.extract(prompt, [SelectPath])
                chosen = args.get("path") if isinstance(args, dict) else None
                if isinstance(chosen, str) and chosen in paths:
                    active_path = chosen
                    path_locked = True
                    # Compute next prompt from the path flow
                    compiled = self._path_compiled.get(active_path) or self._compiled
                    p_engine = Engine(compiled)
                    p_state = p_engine.start()
                    p_state.answers.update(state.answers)
                    follow = p_engine.step(p_state)

        # 4) Persist
        to_save = {"answers": state.answers, "active_path": active_path, "path_locked": path_locked}
        self.deps.store.save(self.user_id, self.agent_type, to_save)

        # 5) Choose reply: next prompt if advanced, else assistant_message or current
        if follow.kind == "terminal":
            return self._escalate("checklist_complete", {"answers": state.answers})
        reply_text = r.assistant_message or (follow.message or out.message or "")
        return AgentResult(outbound=OutboundMessage(text=reply_text), handoff=None, state_diff={})

    def _save_blob(self, blob: AnswersBlob) -> None:
        self.deps.store.save(
            self.user_id,
            self.agent_type,
            blob.model_dump(),
        )
