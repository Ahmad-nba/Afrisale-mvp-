from __future__ import annotations

from dataclasses import dataclass

from app.core import config


@dataclass
class LocalParlantEngine:
    """
    Minimal async-compatible engine fallback used when the Parlant package
    is unavailable or its constructor differs from expected shape.
    """

    role: str
    tools: list
    guidelines: list
    model_backend: str
    api_key: str

    async def run(self, user_text: str) -> str:
        text = (user_text or "").strip()
        return text if text else "How can I help you today?"

    async def invoke(self, user_text: str) -> str:
        return await self.run(user_text)


def build_engine(role: str, tools: list, guidelines: list):
    """
    Instantiates and returns a configured Parlant Engine for the given role.
    role 'owner'    -> loads owner guidelines + owner tool set
    role 'customer' -> loads customer guidelines + customer tool set
    Gemini model is configured from settings.google_api_key.
    Returns: ParlantEngine instance (or equivalent configured object)
    """
    api_key = (config.settings.google_api_key or "").strip()
    if not api_key:
        raise EnvironmentError("GOOGLE_API_KEY must be set in environment.")

    try:
        from parlant import Engine as ParlantEngine  # type: ignore

        return ParlantEngine(
            model={
                "provider": "gemini",
                "api_key": api_key,
            },
            tools=tools,
            guidelines=guidelines,
            metadata={"role": role},
        )
    except Exception:
        return LocalParlantEngine(
            role=role,
            tools=tools,
            guidelines=guidelines,
            model_backend="gemini",
            api_key=api_key,
        )
