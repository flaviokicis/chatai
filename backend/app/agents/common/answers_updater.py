from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable


def _normalize_dict_like(value: object) -> dict[str, Any]:
    """Return a dict for value, parsing JSON strings if needed; otherwise empty dict.

    This is defensive against LLM tool call args that may arrive as JSON strings.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def extract_normalized_updates(tool_args: dict[str, object] | str) -> dict[str, Any]:
    """Extract and normalize the 'updates' dict from tool args in a robust way.

    - Accepts args as dict or JSON string
    - Accepts updates as dict or JSON string
    - Returns an empty dict when absent or invalid
    """
    args = _normalize_dict_like(tool_args)
    # Support UpdateAnswers and UnknownAnswer(tool) shapes
    if isinstance(args, dict) and args.get("__tool_name__") == "UnknownAnswer":
        field = args.get("field")
        if isinstance(field, str) and field:
            return {field: "unknown"}
        # No field provided: caller should interpret as pending field
        return {}
    updates = args.get("updates") if isinstance(args, dict) else {}
    return _normalize_dict_like(updates)


def filter_updates_to_allowed_keys(
    updates: dict[str, Any], allowed_keys: Iterable[str]
) -> dict[str, Any]:
    allowed = set(allowed_keys)
    return {k: v for k, v in updates.items() if k in allowed}


def apply_updates_conservatively(
    *,
    answers: dict[str, Any],
    updates: dict[str, Any],
    pending_field: str | None,
    allowed_keys: Iterable[str] | None = None,
) -> tuple[dict[str, Any], str | None, list[str]]:
    """Apply updates without overwriting existing non-empty values.

    - Optionally restrict updates to allowed keys
    - Only set keys that are currently missing (None or "")
    - Clear pending_field if it becomes non-empty
    - Returns (new_answers, new_pending_field, applied_keys)
    """
    if allowed_keys is not None:
        updates = filter_updates_to_allowed_keys(updates, allowed_keys)

    applied: list[str] = []
    next_answers = dict(answers)
    for key, value in updates.items():
        if key not in next_answers or next_answers.get(key) in (None, ""):
            next_answers[key] = value
            applied.append(key)

    next_pending = pending_field
    if (
        pending_field
        and pending_field in next_answers
        and next_answers[pending_field] not in (None, "")
    ):
        next_pending = None

    return next_answers, next_pending, applied
