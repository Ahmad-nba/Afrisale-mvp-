import logging

from sqlalchemy.orm import Session

from app.parlant_agent.engine import build_engine
from app.parlant_agent.guidelines import customer_guidelines, owner_guidelines
from app.parlant_agent.tool_registry import build_customer_tools, build_owner_tools


logger = logging.getLogger(__name__)


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

    async def run_turn(self, db: Session, user_text: str) -> str:
        """
        Submits user_text to Parlant Engine for this session.
        Returns raw assistant reply string.
        Engine may call tools zero or more times before returning.
        """
        try:
            is_customer = self.role == "customer"
            guidelines = customer_guidelines() if is_customer else owner_guidelines()
            tools = build_customer_tools(db, self.customer_id) if is_customer else build_owner_tools(db)
            engine = build_engine(self.role, tools, guidelines)

            if hasattr(engine, "run_turn"):
                out = await engine.run_turn(user_text)
            elif hasattr(engine, "run"):
                out = await engine.run(user_text)
            elif hasattr(engine, "invoke"):
                out = await engine.invoke(user_text)
            else:
                raise RuntimeError("Engine does not expose an async run method.")
            return str(out or "")
        except Exception:
            logger.exception("AfrisaleSession.run_turn failed")
            return "I'm having trouble right now. Please try again shortly."
