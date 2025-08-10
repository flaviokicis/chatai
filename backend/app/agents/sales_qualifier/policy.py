from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.common.question_graph import QuestionGraph

    from .schemas import SalesQualifierState


class SalesQualifierPolicy:
    def __init__(self, question_graph: QuestionGraph) -> None:
        self.qg = question_graph

    def next_prompt(self, state: SalesQualifierState) -> str | None:
        next_q = self.qg.next_missing(state)
        if not next_q:
            return None
        return next_q.prompt

    def should_escalate(self, state: SalesQualifierState) -> bool:
        # Placeholder heuristic; concrete logic to be added later
        return False
