from sqlalchemy.orm import Session


class OutputValidationGuardrail:
    """
    STRICT post-agent gate. Blocks hallucinated prices, wrong product names,
    and unsafe content before the response is ever formatted or sent.
    Failure triggers fallback response — never silently mangles.
    """

    def validate(self, db: Session, reply: str) -> tuple[bool, str]:
        """
        Returns: (is_valid: bool, safe_fallback_or_empty: str)
        If invalid: safe_fallback_or_empty contains the fallback message to send.
        If valid: safe_fallback_or_empty is empty string.
        """
        pass
