class InputGuardrail:
    """
    Validates inbound message before it reaches the Parlant runtime.
    All checks are fast and synchronous. Does not call the LLM.
    """

    def validate(self, text: str) -> tuple[bool, str]:
        """
        Returns: (is_valid: bool, reason: str)
        reason is empty string on valid.
        Checks: min/max length, not empty, basic intent signal.
        """
        pass
