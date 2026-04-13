from sqlalchemy.orm import Session


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
        pass

    async def run_turn(self, db: Session, user_text: str) -> str:
        """
        Submits user_text to Parlant Engine for this session.
        Returns raw assistant reply string.
        Engine may call tools zero or more times before returning.
        """
        pass
