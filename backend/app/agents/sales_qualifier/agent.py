from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.common.questionnaire_agent import QuestionnaireAgent

from .extractor import SalesExtractor

if TYPE_CHECKING:  # import only for typing
    from app.agents.base import BaseAgentDeps
    from app.agents.common.question_graph import QuestionGraph


class SalesQualifierAgent(QuestionnaireAgent):
    agent_type = "sales_qualifier"

    def __init__(self, user_id: str, deps: BaseAgentDeps, question_graph: QuestionGraph) -> None:
        # Initialize as a QuestionnaireAgent (sets qg, policy, and default extractor)
        super().__init__(user_id, deps, question_graph)
        # Override extractor with domain alias to be explicit about intent
        self.extractor = SalesExtractor(deps.llm)
