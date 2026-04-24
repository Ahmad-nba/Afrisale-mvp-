from __future__ import annotations

import asyncio

from app.parlant_agent.providers.base import ProviderError


class GeminiProvider:
    name = "gemini"

    def __init__(self, *, project_id: str, location: str, model: str, timeout_seconds: float) -> None:
        self.project_id = (project_id or "").strip()
        self.location = (location or "").strip() or "us-central1"
        self.model = (model or "").strip()
        self.timeout_seconds = float(timeout_seconds)

    async def generate(self, prompt: str) -> str:
        if not self.project_id:
            raise ProviderError(provider=self.name, message="Missing GCP project ID.", retryable=False)

        from google import genai

        client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.location,
        )
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
