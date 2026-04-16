import re


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
        s = (text or "").strip()
        if not s:
            return False, "empty_message"
        if len(s) < 1: #cause native user inputs like "k, y, u" are valid
            return False, "too_short"
        if len(s) > 1000:
            return False, "too_long"
        if not re.search(r"[A-Za-z]", s): #also include figures 
            return False, "no_intent"
        return True, ""
