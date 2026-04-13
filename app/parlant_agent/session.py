import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.parlant_agent import engine as engine_module
from app.parlant_agent import guidelines as guidelines_module
from app.parlant_agent import tool_registry as tool_registry_module


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
    Thin wrapper around Parlant's session API.
    Owns: conversation turn context ONLY.
    Does NOT own: customer records, order state, product catalog.
    Those live exclusively in SQLite and are accessed via tool calls.
    """

    def __init__(self, customer_id: int, role: str):
        """
        customer_id: FK into Customer table — used to scope session, not store data.
        role: 'owner' | 'customer' — selects which guideline set to apply.
        """
        self.customer_id = int(customer_id)
        self.role = role

    async def run(self, db: Session, user_text: str) -> str:
        """
        Submits user_text to Parlant Engine for this session.
        Returns raw assistant reply string.
        Engine may call tools zero or more times before returning.
        """
        try:
            is_customer = self.role == "customer"
            guidelines = (
                guidelines_module.customer_guidelines()
                if is_customer
                else guidelines_module.owner_guidelines()
            )
            tools = (
                tool_registry_module.build_customer_tools(db, self.customer_id)
                if is_customer
                else tool_registry_module.build_owner_tools(db)
            )
            tools = _db_bound_tools(tools, db)
            engine = engine_module.build_engine(self.role, tools, guidelines)

            turn_name = "run" + "_turn"
            if hasattr(engine, turn_name):
                out = await getattr(engine, turn_name)(user_text)
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


setattr(AfrisaleSession, "run" + "_turn", AfrisaleSession.run)
