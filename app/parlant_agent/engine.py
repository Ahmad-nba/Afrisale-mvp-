from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
import json
import os
import re
from typing import Any

from app.core import config
from app.observability import logger as obs_logger
from app.parlant_agent.providers.gemini_provider import GeminiProvider
from app.parlant_agent.providers.base import ProviderError


@dataclass
class LocalParlantEngine:
    """
    Minimal async-compatible engine that calls Gemini directly.
    Used when the Parlant package is unavailable.
    """

    role: str
    tools: list
    guidelines: list
    model_backend: str
    provider: GeminiProvider
    retry_attempts: int
    retry_backoff_seconds: float
    recent_messages: list[dict[str, str]] = field(default_factory=list)
    memory_state: dict[str, Any] = field(default_factory=dict)
    save_state: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def set_memory_context(
        self,
        recent_messages: list[dict[str, str]] | None = None,
        memory_state: dict[str, Any] | None = None,
        save_state: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.recent_messages = list(recent_messages or [])
        self.memory_state = dict(memory_state or {})
        self.save_state = save_state

    @staticmethod
    def _format_history(messages: list[dict[str, str]]) -> str:
        if not messages:
            return "- (no recent history)"
        lines: list[str] = []
        for item in messages[-6:]:
            direction = str(item.get("direction", "")).strip().lower()
            role = "User" if direction == "in" else "Assistant"
            text = str(item.get("message", "")).strip()
            if text:
                lines.append(f"- {role}: {text}")
        return "\n".join(lines) if lines else "- (no recent history)"

    @staticmethod
    def _extract_price(text: str) -> int | None:
        matches = re.findall(r"(\d[\d,]{2,})", text or "")
        if not matches:
            return None
        try:
            return int(matches[-1].replace(",", ""))
        except ValueError:
            return None

    @staticmethod
    def _extract_delivery_location(text: str) -> str:
        m = re.search(r"\b(?:to|at|deliver to)\s+([A-Za-z][A-Za-z\s\-]{1,40})", text or "", flags=re.I)
        if not m:
            return ""
        return m.group(1).strip()

    @staticmethod
    def _mentions_reference(text: str) -> bool:
        t = (text or "").lower()
        markers = ("the black one", "the brown one", "the one", "that one", "same one", "black one", "brown one")
        return any(marker in t for marker in markers)

    @staticmethod
    def _extract_color_hint(text: str) -> str:
        t = (text or "").lower()
        for color in ("black", "brown", "white", "blue", "red", "green"):
            if color in t:
                return color
        return ""

    def _resolve_followup_query(self, user_text: str, state: dict[str, Any]) -> str:
        candidates = state.get("lastProductCandidates")
        if not isinstance(candidates, list) or not candidates:
            return (user_text or "").strip()
        if not self._mentions_reference(user_text):
            return (user_text or "").strip()

        hinted_price = self._extract_price(user_text)
        color_hint = self._extract_color_hint(user_text)

        scored: list[tuple[int, dict[str, Any]]] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            score = 0
            title = str(item.get("title", "")).lower()
            price = int(item.get("price", 0) or 0)
            if color_hint and color_hint in title:
                score += 2
            if hinted_price and hinted_price == price:
                score += 2
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        top = scored[0][1] if scored else candidates[0]
        title = str(top.get("title", "")).strip()
        if title:
            return title
        return (user_text or "").strip()

    def _persist_state(self, state: dict[str, Any]) -> dict[str, Any]:
        if callable(self.save_state):
            try:
                self.memory_state = dict(self.save_state(state))
                return self.memory_state
            except Exception:
                self.memory_state = dict(state)
                return self.memory_state
        self.memory_state = dict(state)
        return self.memory_state

    def _build_prompt(self, user_text: str, tool_result: str = "") -> str:
        guideline_lines = []
        for g in self.guidelines:
            guideline_lines.append(f"- {g}")
        tools_summary = []
        for t in self.tools:
            if not isinstance(t, dict):
                continue
            name = str(t.get("name", "unknown_tool"))
            desc = str(t.get("description", ""))
            params = t.get("parameters", {})
            try:
                params_str = json.dumps(params, ensure_ascii=True)
            except Exception:
                params_str = "{}"
            tools_summary.append(f"- {name}: {desc} | params={params_str}")
        memory_state_str = json.dumps(self.memory_state or {}, ensure_ascii=True, default=str)
        history = self._format_history(self.recent_messages or [])
        prompt = (
            f"You are Afrisale assistant for role={self.role}.\n"
            "Follow these guidelines strictly:\n"
            f"{chr(10).join(guideline_lines) if guideline_lines else '- (no guidelines provided)'}\n\n"
            "Recent conversation history (oldest to newest):\n"
            f"{history}\n\n"
            "Structured memory slots:\n"
            f"{memory_state_str}\n\n"
            "Available tools:\n"
            f"{chr(10).join(tools_summary) if tools_summary else '- (no tools provided)'}\n\n"
            f"User message:\n{(user_text or '').strip()}\n\n"
            f"{tool_result}"
            "Respond with the best helpful answer for this turn."
        )
        return prompt

    def _tool_map(self) -> dict[str, Any]:
        mapped: dict[str, Any] = {}
        for t in self.tools:
            if isinstance(t, dict):
                name = str(t.get("name", "")).strip()
                handler = t.get("handler")
                if name and callable(handler):
                    mapped[name] = handler
        return mapped

    async def _generate_with_retry(self, prompt: str, stage: str) -> str:
        attempts = max(1, int(self.retry_attempts))
        for idx in range(attempts):
            try:
                obs_logger.fire_and_forget(
                    obs_logger.log_provider_event(stage, "gemini", "attempt", f"attempt={idx + 1}/{attempts}")
                )
                text = (await self.provider.generate(prompt)).strip()
                obs_logger.fire_and_forget(
                    obs_logger.log_provider_event(stage, "gemini", "success")
                )
                return text
            except ProviderError as exc:
                obs_logger.fire_and_forget(
                    obs_logger.log_provider_event(
                        stage, "gemini", "error",
                        f"retryable={exc.retryable} status={exc.status_code} msg={exc.message[:120]}",
                    )
                )
                if idx == attempts - 1 or not exc.retryable:
                    raise
                await asyncio.sleep(float(self.retry_backoff_seconds) * (idx + 1))
        raise ProviderError(provider="gemini", message="Retries exhausted.", retryable=False)

    @staticmethod
    def _extract_json_block(text: str) -> dict[str, Any]:
        candidate = (text or "").strip()
        if not candidate:
            return {}
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass
        m = re.search(r"\{.*\}", candidate, flags=re.S)
        if not m:
            return {}
        try:
            parsed = json.loads(m.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    async def run(self, user_text: str) -> str:
        tools = self._tool_map()
        state = dict(self.memory_state or {})
        extracted_price = self._extract_price(user_text)
        if extracted_price:
            state["lastMentionedPrice"] = extracted_price
        maybe_location = self._extract_delivery_location(user_text)
        if maybe_location:
            state["deliveryLocation"] = maybe_location
        self._persist_state(state)

        planner_prompt = (
            self._build_prompt(user_text)
            + "\n\nDecide whether a tool call is needed.\n"
            + "Return ONLY JSON with this schema:\n"
            + '{"tool": "<tool_name_or_null>", "args": {}}'
            + "\nRules:\n"
            + "- If user is searching for products, prefer search_products.\n"
            + "- If user asks for full listing, use get_catalog.\n"
            + "- If no tool is needed, set tool to null.\n"
        )
        planner_text = await self._generate_with_retry(planner_prompt, stage="planner")
        plan = self._extract_json_block(planner_text)
        selected_tool = plan.get("tool")
        args = plan.get("args") if isinstance(plan.get("args"), dict) else {}
        if isinstance(selected_tool, str) and selected_tool == "search_products":
            query = str(args.get("query", "")).strip()
            if not query or self._mentions_reference(query):
                args["query"] = self._resolve_followup_query(user_text, self.memory_state)
        if isinstance(selected_tool, str) and selected_tool == "create_order":
            if not args.get("delivery_location"):
                fallback_location = str(self.memory_state.get("deliveryLocation", "")).strip()
                if fallback_location:
                    args["delivery_location"] = fallback_location
            items = args.get("items")
            if (not isinstance(items, list) or not items) and self.memory_state.get("selectedVariantId"):
                args["items"] = [
                    {
                        "variant_id": int(self.memory_state["selectedVariantId"]),
                        "quantity": 1,
                    }
                ]

        tool_context = ""
        tool_result_for_fallback = ""
        if isinstance(selected_tool, str) and selected_tool in tools:
            try:
                tool_result = tools[selected_tool](**args)
                try:
                    from app.parlant_agent import tool_registry as tool_registry_module

                    update = tool_registry_module.derive_memory_update(selected_tool, args, tool_result)
                    if update:
                        new_state = dict(self.memory_state or {})
                        new_state.update(update)
                        self._persist_state(new_state)
                except Exception:
                    pass
                tool_result_for_fallback = json.dumps(tool_result, ensure_ascii=True, default=str)
                tool_context = (
                    "\nTool execution:\n"
                    f"- tool: {selected_tool}\n"
                    f"- args: {json.dumps(args, ensure_ascii=True)}\n"
                    f"- result: {tool_result_for_fallback}\n\n"
                    "Use the tool result above when crafting your response."
                )
            except Exception as exc:
                tool_result_for_fallback = f"ERROR {exc}"
                tool_context = (
                    "\nTool execution:\n"
                    f"- tool: {selected_tool}\n"
                    f"- args: {json.dumps(args, ensure_ascii=True)}\n"
                    f"- result: ERROR {exc}\n\n"
                    "Explain the failure briefly and ask for corrected details."
                )

        final_prompt = self._build_prompt(user_text, tool_result=tool_context)
        try:
            text = await self._generate_with_retry(final_prompt, stage="final")
        except Exception:
            if isinstance(selected_tool, str) and selected_tool in tools:
                return (
                    "I used the requested catalog workflow and got this result:\n"
                    f"{tool_result_for_fallback or 'No tool output available.'}"
                )
            raise
        if text:
            return text
        return "I can help with products, orders, and store support. What do you need?"

    async def invoke(self, user_text: str) -> str:
        return await self.run(user_text)


def build_engine(role: str, tools: list, guidelines: list):
    """
    Instantiates and returns a configured Parlant Engine for the given role.
    Uses Gemini through Vertex AI (GCP) as the sole LLM provider.
    """
    settings = config.settings

    project_id = (settings.gcp_project_id or "").strip()
    if not project_id:
        raise EnvironmentError("GCP_PROJECT_ID must be set in environment.")
    location = (settings.gcp_location or "").strip() or "us-central1"
    credentials_path = (settings.google_application_credentials or "").strip()
    if credentials_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

    model = (settings.gcp_model or settings.gemini_model or "").strip() or "gemini-2.5-flash"
    timeout = float(settings.llm_timeout_seconds)
    retry_attempts = int(settings.llm_retry_attempts)
    retry_backoff = float(settings.llm_retry_backoff_seconds)

    provider = GeminiProvider(
        project_id=project_id,
        location=location,
        model=model,
        timeout_seconds=timeout,
    )

    try:
        from parlant import Engine as ParlantEngine  # type: ignore

        return ParlantEngine(
            model={
                "provider": "gemini",
                "project": project_id,
                "location": location,
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
            provider=provider,
            retry_attempts=retry_attempts,
            retry_backoff_seconds=retry_backoff,
        )
