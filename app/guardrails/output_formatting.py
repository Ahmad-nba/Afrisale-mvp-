import re


_THINK_TAG_RE = re.compile(r"(?is)<think>.*?</think>")
_INTERNAL_TOKEN_RE = re.compile(r"(?i)\[INTERNAL:[^\]]*]")
_BLANK_LINES_RE = re.compile(r"\n\s*\n\s*\n+")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?](?:\s|$)")


class OutputFormattingGuardrail:
    """
    Shapes a validated reply into channel-appropriate format.
    Runs ONLY after OutputValidationGuardrail passes.
    """

    def format(self, reply: str, channel: str = "whatsapp", as_caption: bool = False) -> str:
        """
        channel: 'whatsapp' | 'sms'
        Applies: WhatsApp markdown, length limits per channel,
        line break normalisation, strips internal chain-of-thought tokens.

        When `as_caption` is true the WhatsApp caption limit (1024 chars)
        applies, since Twilio attaches the body to a media message.
        """
        text = self._normalize_common(reply or "")
        if channel.lower() == "sms":
            text = self._strip_markdown(text)
            return self._truncate_sms(text)
        if as_caption:
            return self._truncate_caption(text)
        return self._truncate_whatsapp(text)

    @staticmethod
    def _normalize_common(text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = _THINK_TAG_RE.sub("", normalized)
        normalized = _INTERNAL_TOKEN_RE.sub("", normalized)
        normalized = _BLANK_LINES_RE.sub("\n\n", normalized)
        return normalized.strip()

    @staticmethod
    def _strip_markdown(text: str) -> str:
        text = _MARKDOWN_LINK_RE.sub(r"\1", text)
        return re.sub(r"[*_~`]", "", text)

    @staticmethod
    def _truncate_whatsapp(text: str) -> str:
        max_len = 1600
        if len(text) <= max_len:
            return text
        chunk = text[: max_len - 1]
        last_boundary_end = -1
        for m in _SENTENCE_BOUNDARY_RE.finditer(chunk):
            last_boundary_end = m.end()
        if last_boundary_end > 0:
            return chunk[:last_boundary_end].rstrip() + "…"
        last_space = chunk.rfind(" ")
        if last_space > 0:
            return chunk[:last_space].rstrip() + "…"
        return chunk.rstrip() + "…"

    @staticmethod
    def _truncate_sms(text: str) -> str:
        max_len = 160
        if len(text) <= max_len:
            return text
        chunk = text[: max_len - 1]
        last_space = chunk.rfind(" ")
        if last_space > 0:
            return chunk[:last_space].rstrip() + "…"
        return chunk.rstrip() + "…"

    @staticmethod
    def _truncate_caption(text: str) -> str:
        max_len = 1024
        if len(text) <= max_len:
            return text
        chunk = text[: max_len - 1]
        last_boundary_end = -1
        for m in _SENTENCE_BOUNDARY_RE.finditer(chunk):
            last_boundary_end = m.end()
        if last_boundary_end > 0:
            return chunk[:last_boundary_end].rstrip() + "…"
        last_space = chunk.rfind(" ")
        if last_space > 0:
            return chunk[:last_space].rstrip() + "…"
        return chunk.rstrip() + "…"
