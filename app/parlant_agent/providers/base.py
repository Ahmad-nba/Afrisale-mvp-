from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ProviderError(Exception):
    provider: str
    message: str
    retryable: bool = False
    status_code: int | None = None

    def __str__(self) -> str:
        return f"{self.provider}: {self.message}"


class LLMProvider(Protocol):
    name: str

    async def generate(self, prompt: str) -> str:
        """Generate a text response for a prompt."""
