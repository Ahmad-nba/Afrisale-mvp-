from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import re
from typing import Any

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
    model_name: str

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
        prompt = (
            f"You are Afrisale assistant for role={self.role}.\n"
            "Follow these guidelines strictly:\n"
            f"{chr(10).join(guideline_lines) if guideline_lines else '- (no guidelines provided)'}\n\n"
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

    async def _generate_with_retry(self, client, prompt: str) -> Any:
        attempts = 3
        for idx in range(attempts):
            try:
                return await client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )
            except Exception as exc:
                msg = str(exc).lower()
                is_retryable = "503" in msg or "unavailable" in msg or "timeout" in msg
                if idx == attempts - 1 or not is_retryable:
                    raise
                await asyncio.sleep(0.8 * (idx + 1))
        raise RuntimeError("LLM generation failed after retries.")

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
        from google import genai

        client = genai.Client(api_key=self.api_key)
        tools = self._tool_map()
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
        planner_resp = await self._generate_with_retry(client, planner_prompt)
        plan = self._extract_json_block(getattr(planner_resp, "text", "") or "")
        selected_tool = plan.get("tool")
        args = plan.get("args") if isinstance(plan.get("args"), dict) else {}

        tool_context = ""
        tool_result_for_fallback = ""
        if isinstance(selected_tool, str) and selected_tool in tools:
            try:
                tool_result = tools[selected_tool](**args)
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
            response = await self._generate_with_retry(client, final_prompt)
        except Exception:
            if isinstance(selected_tool, str) and selected_tool in tools:
                return (
                    "I used the requested catalog workflow and got this result:\n"
                    f"{tool_result_for_fallback or 'No tool output available.'}"
                )
            raise
        text = (getattr(response, "text", None) or "").strip()
        if text:
            return text
        return "I can help with products, orders, and store support. What do you need?"

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
            model_name=(config.settings.gemini_model or "gemini-2.5-flash"),
        )
