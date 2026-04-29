import re


class InputGuardrail:
    """
    Validates inbound message before it reaches the Parlant runtime.
    All checks are fast and synchronous. Does not call the LLM.
    """

    def validate(self, text: str, has_attachments: bool = False) -> tuple[bool, str]:
        """
        Returns: (is_valid: bool, reason: str)
        reason is empty string on valid.
        Checks: min/max length, not empty, basic intent signal.

        When the inbound message carries one or more attachments, the text
        body is allowed to be empty (e.g., user sends only a reference image).
        """
        s = (text or "").strip()
        if has_attachments:
            if len(s) > 1000:
                return False, "too_long"
            return True, ""

        if not s:
            return False, "empty_message"
        if len(s) < 1:
            return False, "too_short"
        if len(s) > 1000:
            return False, "too_long"
        if not re.search(r"[A-Za-z]", s):
            return False, "no_intent"
        return True, ""
