from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .normalize import choose_option

GuardFunction = Callable[[dict[str, Any]], bool]


def guard_always(_ctx: dict[str, Any]) -> bool:
    return True


def guard_answers_has(ctx: dict[str, Any]) -> bool:
    answers = ctx.get("answers")
    key = ctx.get("key")
    if not isinstance(answers, dict) or not isinstance(key, str):
        return False
    value = answers.get(key)
    return value not in (None, "")


def guard_answers_equals(ctx: dict[str, Any]) -> bool:
    answers = ctx.get("answers")
    key = ctx.get("key")
    expected = ctx.get("value")
    if not isinstance(answers, dict) or not isinstance(key, str):
        return False
    actual = answers.get(key)
    if actual == expected:
        return True
    # If provided, allow fuzzy match through allowed_values in context
    allowed = ctx.get("allowed_values")
    if isinstance(actual, str) and isinstance(expected, str) and isinstance(allowed, list):
        canonical = choose_option(actual, allowed)
        return canonical == expected
    return False


def guard_path_locked(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("path_locked")) and isinstance(ctx.get("active_path"), str)


def guard_deps_missing(ctx: dict[str, Any]) -> bool:
    """Return True if all dependencies are satisfied and the target key is missing.

    Expects in ctx:
    - answers: dict[str, Any]
    - key: str
    - dependencies: list[str]
    """
    answers = ctx.get("answers")
    key = ctx.get("key")
    deps = ctx.get("dependencies")
    if not isinstance(answers, dict) or not isinstance(key, str):
        return False
    if not isinstance(deps, list):
        deps = []
    # All dependencies must be present (non-empty)
    for dep in deps:
        if not isinstance(dep, str):
            return False
        if answers.get(dep) in (None, ""):
            return False
    # And the key itself must be missing
    return answers.get(key) in (None, "")


DEFAULT_GUARDS: dict[str, GuardFunction] = {
    "always": guard_always,
    "answers_has": guard_answers_has,
    "answers_equals": guard_answers_equals,
    "path_locked": guard_path_locked,
    "deps_missing": guard_deps_missing,
}
