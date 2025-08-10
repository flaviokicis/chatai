from __future__ import annotations


def choose_option(user_message: str, allowed_values: list[str]) -> str | None:
    """Return the best matching canonical option for a free-text message.

    Strategy: casefold, underscore -> space, substring check, simple token overlap.
    Deterministic and side-effect free; does not mutate input.
    """
    text = " ".join(user_message.lower().split())
    best: tuple[int, str] | None = None
    for val in allowed_values:
        v = val.lower().replace("_", " ")
        score = 0
        if v in text:
            score += 3
        v_tokens = [t for t in v.split() if t]
        match_tokens = sum(1 for t in v_tokens if t in text)
        score += match_tokens
        if score > 0 and (best is None or score > best[0]):
            best = (score, val)
    return best[1] if best else None
