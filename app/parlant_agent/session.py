import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.parlant_agent import engine as engine_module
from app.parlant_agent import guidelines as guidelines_module
from app.parlant_agent import tool_registry as tool_registry_module
from app.services import conversation_state_service, message_service


logger = logging.getLogger(__name__)


def _db_bound_tools(tools: list, db: Session) -> list:
    """Bind db into each tool handler so engine can call handler(**kwargs)."""
    bound: list = []
    for tool in tools:
        if not isinstance(tool, dict):
            bound.append(tool)
            continue
        handler = tool.get("handler")
        if not callable(handler):
            bound.append(tool)
            continue

        def _make_bound(h: Callable):
            def _bound_handler(**kwargs):
                return h(db, **kwargs)

            return _bound_handler

        patched = dict(tool)
        patched["handler"] = _make_bound(handler)
        bound.append(patched)
    return bound


class AfrisaleSession:
    """
    Thin wrapper around the agent engine.
    Owns: conversation turn context ONLY.
    Does NOT own: customer records, order state, product catalog.
    Those live exclusively in SQLite and are accessed via tool calls.
    """

    def __init__(self, customer_id: int, role: str):
        self.customer_id = int(customer_id)
        self.role = role

    async def _build_engine_with_context(
        self,
        db: Session,
        attachments: list[dict[str, Any]] | None = None,
    ):
        is_customer = self.role == "customer"
        guidelines = (
            guidelines_module.customer_guidelines()
            if is_customer
            else guidelines_module.owner_guidelines()
        )
        memory_state = conversation_state_service.get_state(db, self.customer_id)
        if attachments:
            memory_state["lastInboundAttachments"] = list(attachments)

        tools = (
            tool_registry_module.build_customer_tools(
                db,
                self.customer_id,
                last_attachments=attachments,
                last_memory_state=memory_state,
            )
            if is_customer
            else tool_registry_module.build_owner_tools(db, last_attachments=attachments)
        )

        recent_rows = message_service.get_recent_messages(db, self.customer_id, limit=6)
        recent_messages = [
            {"direction": m.direction, "message": m.message}
            for m in recent_rows
        ]

        tools = _db_bound_tools(tools, db)
        engine = engine_module.build_engine(self.role, tools, guidelines)
        if hasattr(engine, "set_memory_context"):
            engine.set_memory_context(
                recent_messages=recent_messages,
                memory_state=memory_state,
                save_state=lambda state: conversation_state_service.save_state(
                    db,
                    self.customer_id,
                    state,
                ),
            )
        if hasattr(engine, "set_attachments"):
            engine.set_attachments(list(attachments or []))
        return engine

    async def run(self, db: Session, user_text: str) -> str:
        """Backwards-compatible text-only entry point."""
        try:
            engine = await self._build_engine_with_context(db, attachments=None)
            run_name = "run" + "_turn"
            if hasattr(engine, run_name):
                out = await getattr(engine, run_name)(user_text)
            elif hasattr(engine, "run"):
                out = await engine.run(user_text)
            elif hasattr(engine, "invoke"):
                out = await engine.invoke(user_text)
            else:
                raise RuntimeError("Engine does not expose an async run method.")
            return str(out or "")
        except Exception:
            logger.exception("AfrisaleSession turn failed")
            return "I'm having trouble right now. Please try again shortly."

    async def run_turn_with_media(
        self,
        db: Session,
        user_text: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Runs a turn with optional inbound media context and returns a dict:
            {
              "reply": str,            # caption when media is present, else free-form reply
              "media_url": str,        # public https URL of top match's image (empty if none)
              "media_gcs_uri": str,    # gs:// URI for signing at dispatch time
              "alternates_text": str,  # follow-up text listing additional matches
              "matches": list,         # full match dicts
            }
        """
        try:
            engine = await self._build_engine_with_context(db, attachments=attachments)
            run_name = "run" + "_turn"
            if hasattr(engine, run_name):
                out = await getattr(engine, run_name)(user_text)
            elif hasattr(engine, "run"):
                out = await engine.run(user_text)
            elif hasattr(engine, "invoke"):
                out = await engine.invoke(user_text)
            else:
                raise RuntimeError("Engine does not expose an async run method.")
            reply = str(out or "")
            media_url = ""
            media_gcs_uri = ""
            caption = ""
            alternates = ""
            matches: list[dict[str, Any]] = []
            if hasattr(engine, "consume_media_artifacts"):
                artifacts = engine.consume_media_artifacts()
                media_url = str(artifacts.get("media_url", "") or "")
                media_gcs_uri = str(artifacts.get("media_gcs_uri", "") or "")
                caption = str(artifacts.get("caption", "") or "")
                alternates = str(artifacts.get("alternates_text", "") or "")
                matches = list(artifacts.get("matches") or [])
            # When a media card will be sent we prefer the deterministic
            # caption over the LLM prose; this guarantees the card always
            # shows name, price, and variants in a stable layout.
            if media_url and caption:
                reply = caption
            return {
                "reply": reply,
                "media_url": media_url,
                "media_gcs_uri": media_gcs_uri,
                "alternates_text": alternates,
                "matches": matches,
            }
        except Exception:
            logger.exception("AfrisaleSession media turn failed")
            return {
                "reply": "I'm having trouble right now. Please try again shortly.",
                "media_url": "",
                "media_gcs_uri": "",
                "alternates_text": "",
                "matches": [],
            }


setattr(AfrisaleSession, "run" + "_turn", AfrisaleSession.run)
