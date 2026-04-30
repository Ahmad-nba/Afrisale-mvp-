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
    attachments: list[dict[str, Any]] = field(default_factory=list)
    _media_artifacts: dict[str, Any] = field(default_factory=dict)

    def set_memory_context(
        self,
        recent_messages: list[dict[str, str]] | None = None,
        memory_state: dict[str, Any] | None = None,
        save_state: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.recent_messages = list(recent_messages or [])
        self.memory_state = dict(memory_state or {})
        self.save_state = save_state

    def set_attachments(self, attachments: list[dict[str, Any]] | None = None) -> None:
        self.attachments = list(attachments or [])

    def consume_media_artifacts(self) -> dict[str, Any]:
        """
        Returns and clears the media artifacts captured during the last turn:
            { "media_url": str, "alternates_text": str, "matches": list }
        Called by the session after `run_turn` to drive WhatsApp media dispatch.
        """
        artifacts = dict(self._media_artifacts)
        self._media_artifacts = {}
        return artifacts

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

    def _format_attachments(self) -> str:
        if not self.attachments:
            return "- (no attachments)"
        lines: list[str] = []
        for item in self.attachments:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind", "")) or "unknown"
            mime = str(item.get("mime_type", "")) or "unknown"
            ident = item.get("id", "?")
            lines.append(f"- attachment_id={ident} kind={kind} mime={mime}")
        return "\n".join(lines) if lines else "- (no attachments)"

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
        attachments_block = self._format_attachments()
        prompt = (
            f"You are Afrisale assistant for role={self.role}.\n"
            "Follow these guidelines strictly:\n"
            f"{chr(10).join(guideline_lines) if guideline_lines else '- (no guidelines provided)'}\n\n"
            "Recent conversation history (oldest to newest):\n"
            f"{history}\n\n"
            "Structured memory slots:\n"
            f"{memory_state_str}\n\n"
            "Inbound attachments on this turn:\n"
            f"{attachments_block}\n\n"
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

    @staticmethod
    def _format_alternates(matches: list[dict[str, Any]]) -> str:
        if not matches:
            return ""
        lines: list[str] = ["More options that look similar:"]
        for match in matches:
            if not isinstance(match, dict):
                continue
            name = str(match.get("name", "")).strip() or "Product"
            variants = match.get("variants") or []
            price_str = ""
            if variants:
                first_variant = variants[0] if isinstance(variants[0], dict) else {}
                price_val = first_variant.get("price")
                if isinstance(price_val, (int, float)) and price_val:
                    price_str = f" - {int(price_val):,}"
            lines.append(f"- {name}{price_str}")
        return "\n".join(lines)

    @staticmethod
    def _build_caption(top: dict[str, Any]) -> str:
        """
        Deterministic caption shown alongside a WhatsApp media card.
        Format: "<Name> — <price>\n<size/color summary>\n<short description>".
        Capped to 1024 chars (Twilio caption limit) by output_formatting later.
        """
        if not isinstance(top, dict):
            return ""
        name = str(top.get("name", "")).strip() or "Product"
        variants = top.get("variants") or []
        price_val: int | None = None
        if variants:
            first = variants[0] if isinstance(variants[0], dict) else {}
            raw_price = first.get("price")
            if isinstance(raw_price, (int, float)) and raw_price:
                price_val = int(raw_price)

        header = name
        if price_val is not None:
            header = f"{name} - {price_val:,}"

        variant_summary = ""
        if variants:
            parts: list[str] = []
            for v in variants[:3]:
                if not isinstance(v, dict):
                    continue
                size = str(v.get("size", "")).strip()
                color = str(v.get("color", "")).strip()
                stock = v.get("stock_quantity")
                pieces = "/".join([p for p in (size, color) if p])
                if stock is not None and isinstance(stock, (int, float)):
                    pieces = f"{pieces} (stock {int(stock)})" if pieces else f"stock {int(stock)}"
                if pieces:
                    parts.append(pieces)
            if parts:
                variant_summary = "Variants: " + ", ".join(parts)

        description = str(top.get("description", "") or "").strip()
        if len(description) > 200:
            description = description[:197].rstrip() + "…"

        lines = [header]
        if variant_summary:
            lines.append(variant_summary)
        if description:
            lines.append(description)
        return "\n".join(lines)

    def _has_inbound_image(self) -> bool:
        return any(
            isinstance(a, dict) and str(a.get("kind", "")).lower() == "image"
            for a in (self.attachments or [])
        )

    @staticmethod
    def _is_image_request(text: str) -> bool:
        """Heuristic: user asked to see/share/send an image of a product."""
        t = (text or "").lower().strip()
        if not t:
            return False
        keywords = (
            "share an image",
            "share image",
            "share a photo",
            "share photo",
            "send an image",
            "send image",
            "send a photo",
            "send photo",
            "send me a photo",
            "send me an image",
            "show me a photo",
            "show me an image",
            "show me the image",
            "show me the photo",
            "show the image",
            "picture of it",
            "picture of the",
            "photo of it",
            "photo of the",
            "image of it",
            "image of the",
        )
        return any(k in t for k in keywords)

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

        has_image = self._has_inbound_image()
        wants_image = self._is_image_request(user_text)
        planner_prompt = (
            self._build_prompt(user_text)
            + "\n\nDecide whether a tool call is needed.\n"
            + "Return ONLY JSON with this schema:\n"
            + '{"tool": "<tool_name_or_null>", "args": {}}'
            + "\nRules:\n"
            + "- If the inbound message has an image attachment, you MUST use find_products_by_image (no args needed; latest image is used).\n"
            + "- If the user asks to see, share, or send an image/photo of a product they have already discussed, use get_product_image (no args needed; selectedProductId from memory is used).\n"
            + "- If user is searching for products by description, prefer search_products.\n"
            + "- For descriptive product queries (brand, color, material), prefer find_products_by_text.\n"
            + "- If user asks for full listing, use get_catalog.\n"
            + "- If no tool is needed, set tool to null.\n"
        )
        planner_text = await self._generate_with_retry(planner_prompt, stage="planner")
        plan = self._extract_json_block(planner_text)
        selected_tool = plan.get("tool")
        args = plan.get("args") if isinstance(plan.get("args"), dict) else {}

        # Hard override: if the user actually attached an image, force the
        # image-search tool. Planner sometimes drifts even with rules above.
        if has_image and "find_products_by_image" in tools:
            selected_tool = "find_products_by_image"
            args = {}
        # Hard override: explicit "share an image" intent without an attachment
        # routes to get_product_image so we surface a fresh media card.
        elif wants_image and "get_product_image" in tools:
            selected_tool = "get_product_image"
            args = {}

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
        captured_matches: list[dict[str, Any]] = []
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

                if selected_tool in (
                    "find_products_by_image",
                    "find_products_by_text",
                    "get_product_image",
                    "search_products",
                ) and isinstance(tool_result, list):
                    captured_matches = [m for m in tool_result if isinstance(m, dict)]

                tool_result_for_fallback = json.dumps(tool_result, ensure_ascii=True, default=str)
                tool_context = (
                    "\nTool execution:\n"
                    f"- tool: {selected_tool}\n"
                    f"- args: {json.dumps(args, ensure_ascii=True)}\n"
                    f"- result: {tool_result_for_fallback}\n\n"
                    "Use the tool result above when crafting your response. "
                    "If the result is a list of products, write a friendly WhatsApp-style reply "
                    "that names the top match (with price + key variants). Do NOT invent "
                    "products or prices outside the result. If the result is empty, say we "
                    "do not have a match and offer to help search again."
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
                self._capture_media_artifacts(captured_matches)
                return (
                    "I used the requested catalog workflow and got this result:\n"
                    f"{tool_result_for_fallback or 'No tool output available.'}"
                )
            raise

        self._capture_media_artifacts(captured_matches)
        if text:
            return text
        return "I can help with products, orders, and store support. What do you need?"

    def _capture_media_artifacts(self, matches: list[dict[str, Any]]) -> None:
        """
        Persist a `media_url` for the top match (if it has an image) plus a
        short alternates text so the dispatch stage can render a WhatsApp
        media card + follow-up text.

        Also produces a deterministic `caption` (name + price + variants +
        short description) so the card always renders consistently regardless
        of what the LLM wrote.
        """
        if not matches:
            self._media_artifacts = {}
            return
        top = matches[0] if isinstance(matches[0], dict) else {}
        media_url = str(top.get("image_url") or "")
        if not media_url:
            self._media_artifacts = {}
            return
        caption = self._build_caption(top)
        alternates = self._format_alternates(matches[1:4])
        self._media_artifacts = {
            "media_url": media_url,
            "media_gcs_uri": str(top.get("image_gcs_uri") or ""),
            "caption": caption,
            "alternates_text": alternates,
            "matches": matches,
        }

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
