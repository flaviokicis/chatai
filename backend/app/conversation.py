from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field


class ConversationState(BaseModel):
    intention: str | None = None
    is_sports_court_led: bool | None = None
    sport: str | None = None
    covered_from_rain: bool | None = None
    dimensions: str | None = None
    pending_field: str | None = None

    def is_complete(self) -> bool:
        if not self.intention:
            return False
        if self.is_sports_court_led is None:
            return False
        if self.is_sports_court_led:
            return (
                self.sport is not None
                and self.covered_from_rain is not None
                and self.dimensions is not None
            )
        return True


class UpdateChecklist(BaseModel):
    """Extract or update known checklist fields. Leave fields null if unknown."""

    intention: str | None = Field(default=None, description="User intention in plain language")
    is_sports_court_led: bool | None = Field(
        default=None, description="Whether the user intends to buy LED lights for a sports court"
    )
    sport: str | None = Field(
        default=None, description="Sport for the court, e.g. basketball, tennis"
    )
    covered_from_rain: bool | None = Field(
        default=None,
        description="True if covered from rain (indoor/covered), False if open/outdoor",
    )
    dimensions: str | None = Field(
        default=None, description="Court dimensions like '28 x 15 m' or '94 x 50 ft'"
    )


class ConversationManager:
    def __init__(self) -> None:
        self._store: dict[str, ConversationState] = {}
        self._logger = logging.getLogger("uvicorn.error")

    def get_state(self, user_id: str) -> ConversationState:
        if user_id not in self._store:
            self._store[user_id] = ConversationState()
        return self._store[user_id]

    def apply_update(self, state: ConversationState, update: UpdateChecklist) -> None:
        if update.intention is not None and not state.intention:
            state.intention = update.intention.strip()
        if update.is_sports_court_led is not None and state.is_sports_court_led is None:
            state.is_sports_court_led = update.is_sports_court_led
        if update.sport is not None and not state.sport:
            state.sport = update.sport.strip().lower()
        if update.covered_from_rain is not None and state.covered_from_rain is None:
            state.covered_from_rain = update.covered_from_rain
        if update.dimensions is not None and not state.dimensions:
            state.dimensions = update.dimensions.strip()
        if state.pending_field and (
            (state.pending_field == "is_sports_court_led" and state.is_sports_court_led is not None)
            or (state.pending_field == "sport" and state.sport is not None)
            or (state.pending_field == "covered_from_rain" and state.covered_from_rain is not None)
            or (state.pending_field == "dimensions" and state.dimensions is not None)
        ):
            state.pending_field = None

    def classify_and_update(
        self, state: ConversationState, message: str, llm: BaseChatModel
    ) -> None:
        tools = [UpdateChecklist]
        llm_with_tools = llm.bind_tools(tools)
        state_summary = {
            "intention": state.intention,
            "is_sports_court_led": state.is_sports_court_led,
            "sport": state.sport,
            "covered_from_rain": state.covered_from_rain,
            "dimensions": state.dimensions,
        }
        prompt = (
            "You update a structured checklist for a customer conversation. "
            "Be strictly conservative: extract a field only if the user's latest message EXPLICITLY provides it. "
            "Do not infer or guess. If uncertain, leave the field null. "
            "Rules: "
            "- intention: brief paraphrase of the user's goal if stated; otherwise null. "
            "- is_sports_court_led: set True ONLY if the message explicitly mentions a sports court (e.g., 'sports court', 'court', 'tennis court', 'soccer field') or a sport-specific court, or they previously confirmed. "
            "  Set False ONLY if it explicitly mentions a non-sports application. Otherwise leave null. "
            "- sport / covered_from_rain / dimensions: set only if explicitly given. "
            "If the user's message is a confirmation/denial to the last question, update the specific field accordingly. "
            "You are responsible for interpreting simple confirmations like 'yes/it is' or denials like 'no/not', but only in relation to the last question. "
            "Always respond by calling the UpdateChecklist tool with extracted values.\n\n"
            f"Current known state: {state_summary}\n"
            f"Previous question field key (may be null): {state.pending_field}\n"
            "When the user's message is a bare confirmation/denial (e.g., yes/no), update the field ONLY if the target field is boolean per the tool schema. "
            "For non-boolean targets, do not set values on a generic yes/no; require explicit content from the user. "
            "Never infer; only set what is explicitly answered.\n\n"
            f"User message: {message}"
        )

        result = llm_with_tools.invoke(prompt)
        tool_calls: list[dict[str, object]] = getattr(result, "tool_calls", [])
        if not tool_calls:
            forced_prompt = (
                prompt
                + "\n\nYou must call the UpdateChecklist tool. Set fields you can't determine to null."
            )
            result = llm_with_tools.invoke(forced_prompt)
            tool_calls = getattr(result, "tool_calls", [])

        for tc in tool_calls:
            if tc.get("name") == "UpdateChecklist":
                args = tc.get("args", {}) or {}
                before = {
                    "intention": state.intention,
                    "is_sports_court_led": state.is_sports_court_led,
                    "sport": state.sport,
                    "covered_from_rain": state.covered_from_rain,
                    "dimensions": state.dimensions,
                }
                update = UpdateChecklist(**args)
                self.apply_update(state, update)
                after = {
                    "intention": state.intention,
                    "is_sports_court_led": state.is_sports_court_led,
                    "sport": state.sport,
                    "covered_from_rain": state.covered_from_rain,
                    "dimensions": state.dimensions,
                }
                changes: dict[str, dict[str, object]] = {}
        for key, before_value in before.items():
            if before_value != after[key]:
                changes[key] = {"from": before_value, "to": after[key]}
                if changes:
                    self._logger.info("Tool call UpdateChecklist applied changes: %s", changes)
                else:
                    self._logger.info(
                        "Tool call UpdateChecklist made no effective changes (args=%s)",
                        args,
                    )

    def next_question(self, state: ConversationState) -> str | None:
        if not state.intention:
            state.pending_field = "intention"
            return "What is your intention?"
        if state.is_sports_court_led is None:
            state.pending_field = "is_sports_court_led"
            return "Is your intention to buy LED lights for a sports court?"
        if state.is_sports_court_led:
            if not state.sport:
                state.pending_field = "sport"
                return "Which sport is the court for?"
            if state.covered_from_rain is None:
                state.pending_field = "covered_from_rain"
                return "Is the court covered from rain or is it in the open?"
            if not state.dimensions:
                state.pending_field = "dimensions"
                return "What are the dimensions of the court? (e.g., 28 x 15 m)"
        return None

    def handle(self, user_id: str, message: str, llm: BaseChatModel) -> str:
        state = self.get_state(user_id)
        self.classify_and_update(state, message, llm)
        if state.is_complete():
            return "All good, transfering to human"
        nq = self.next_question(state)
        return nq or "All good, transfering to human"
