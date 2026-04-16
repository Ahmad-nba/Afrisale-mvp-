from __future__ import annotations

import asyncio

from app.parlant_agent.providers.base import ProviderError


class GeminiProvider:
    name = "gemini"

    def __init__(self, *, api_key: str, model: str, timeout_seconds: float) -> None:
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.timeout_seconds = float(timeout_seconds)

    async def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise ProviderError(provider=self.name, message="Missing API key.", retryable=False)

        from google import genai

        client = genai.Client(api_key=self.api_key)
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt,
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ProviderError(provider=self.name, message="Request timed out.", retryable=True) from exc
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            retryable = any(k in msg for k in ("503", "unavailable", "timeout", "429", "rate"))
            status_code = None
            if "503" in msg:
                status_code = 503
            elif "429" in msg:
                status_code = 429
            raise ProviderError(
                provider=self.name,
                message=str(exc),
                retryable=retryable,
                status_code=status_code,
            ) from exc

        text = (getattr(response, "text", None) or "").strip()
        return text
