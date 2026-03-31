import re

_MAX = 500
_KEYWORDS = frozenset(
    "order product price stock size color delivery hello hi help catalog shop buy pay status".split()
)


def validate_inbound_message(text: str | None) -> tuple[bool, str]:
    if text is None:
        return False, "Empty message."
    s = text.strip()
    if not s:
        return False, "Empty message."
    if len(s) > _MAX:
        return False, "Message too long. Please send a shorter message."
    if not _has_recognizable_intent(s):
        return False, "Sorry, I did not understand. Try asking about products, orders, or prices."
    return True, s


def _has_recognizable_intent(s: str) -> bool:
    if re.search(r"[A-Za-z0-9]", s):
        low = s.lower()
        tokens = re.findall(r"[a-z0-9]+", low)
        if any(t in _KEYWORDS for t in tokens):
            return True
        if len(s) >= 3:
            return True
    return False
