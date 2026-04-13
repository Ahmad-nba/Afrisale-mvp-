class OutputFormattingGuardrail:
    """
    Shapes a validated reply into channel-appropriate format.
    Runs ONLY after OutputValidationGuardrail passes.
    """

    def format(self, reply: str, channel: str = "whatsapp") -> str:
        """
        channel: 'whatsapp' | 'sms'
        Applies: WhatsApp markdown, length limits per channel,
        line break normalisation, strips internal chain-of-thought tokens.
        """
        pass
