from __future__ import annotations

from typing import Protocol


class GenerationBackend(Protocol):
    name: str

    def generate(self, prompt: str, *, max_new_tokens: int) -> str: ...
