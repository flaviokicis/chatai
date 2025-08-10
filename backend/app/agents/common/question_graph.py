from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

Validator = Callable[[object], bool]


@dataclass(slots=True, frozen=True)
class Question:
    key: str
    prompt: str
    required: bool = True
    priority: int = 100
    dependencies: list[str] = field(default_factory=list)
    validate: Validator | None = None

    def is_applicable(self, state: object) -> bool:
        """
        Returns True if all dependencies are satisfied in the given state.
        Looks up dependency values from a generic 'answers' dict on state.
        """
        answers = getattr(state, "answers", {})
        if not isinstance(answers, dict):
            return False
        return all(answers.get(dep) not in (None, "") for dep in self.dependencies)

    def is_missing(self, state: object) -> bool:
        """
        Returns True if the value for this question is missing in the given state.
        Expects state to have an 'answers' dict[str, Any].
        """
        answers = getattr(state, "answers", {})
        if not isinstance(answers, dict):
            return True
        value = answers.get(self.key)
        return value in (None, "")


class QuestionGraph:
    def __init__(self, questions: list[Question]) -> None:
        self._questions: dict[str, Question] = {q.key: q for q in questions}

    def next_missing(self, state: object) -> Question | None:
        """
        Returns the next required question whose dependencies are satisfied and value is missing,
        ordered by priority (lowest number first). Returns None if no such question exists.
        This method is robust against empty question lists and missing attributes in state.
        """
        if not self._questions:
            return None

        candidates: list[Question] = []
        for q in self._questions.values():
            try:
                if not q.required:
                    continue
                if not q.is_applicable(state):
                    continue
                if not q.is_missing(state):
                    continue
                candidates.append(q)
            except Exception as exc:
                logging.getLogger(__name__).debug(
                    "Skipping question %s due to error evaluating applicability/missing: %s",
                    q.key,
                    exc,
                )
                continue

        if not candidates:
            return None

        # Defensive: ensure candidates is not empty before calling min
        try:
            return min(candidates, key=lambda q: q.priority)
        except ValueError:
            # Should not occur due to above check, but handle defensively
            return None

    def get_by_prompt(self, prompt: str) -> Question | None:
        for q in self._questions.values():
            if q.prompt == prompt:
                return q
        return None

    def keys(self) -> list[str]:
        return list(self._questions.keys())

    def __iter__(self) -> Iterator[str]:
        return iter(self._questions.keys())

    def get(self, key: str) -> Question | None:
        return self._questions.get(key)

    def items(self) -> Iterator[tuple[str, Question]]:
        return iter(self._questions.items())

    def merge_with(self, other: QuestionGraph) -> QuestionGraph:
        combined: dict[str, Question] = dict(self._questions)
        combined.update(other._questions)
        return QuestionGraph(list(combined.values()))


def build_question_graph_from_params(params: dict[str, object]) -> QuestionGraph:
    def _parse_list(items: list[dict[str, object]] | object) -> list[Question]:
        questions: list[Question] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("key", "")).strip()
                prompt = str(item.get("prompt", "")).strip()
                if not key or not prompt:
                    continue
                priority = int(item.get("priority", 100))
                deps_raw = item.get("dependencies", [])
                deps = [str(d) for d in deps_raw] if isinstance(deps_raw, list) else []
                questions.append(
                    Question(key=key, prompt=prompt, priority=priority, dependencies=deps)
                )
        return questions

    if not isinstance(params, dict):
        return QuestionGraph([])

    cfg = params.get("question_graph")
    # Multi-path shape: { global: [...], paths: { name: { questions: [...] } } }
    if isinstance(cfg, dict) and ("global" in cfg or "paths" in cfg):
        # Build only the global graph here; path-specific graphs are built by utilities
        global_questions: list[Question] = []
        global_questions.extend(_parse_list(cfg.get("global", [])))
        return QuestionGraph(global_questions)

    # Flat list fallback
    return QuestionGraph(_parse_list(cfg))
