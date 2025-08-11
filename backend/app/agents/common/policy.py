from __future__ import annotations

# Deprecated: flow_core now handles prompt selection. This module remains for
# backward compatibility but is not used. Intentionally minimal to avoid import errors.

__all__ = ["QuestionnairePolicy"]


class QuestionnairePolicy:  # pragma: no cover - legacy stub
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def next_prompt(self, _state: object) -> str | None:
        return None

    def should_escalate(self, _state: object) -> bool:
        return False
