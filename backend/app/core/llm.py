from __future__ import annotations

from typing import Any, Protocol


class LLMClient(Protocol):
    def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]: ...
