def build_engine(role: str):
    """
    Instantiates and returns a configured Parlant Engine for the given role.
    role 'owner'    → loads owner guidelines + owner tool set
    role 'customer' → loads customer guidelines + customer tool set
    Gemini model is configured from settings.google_api_key.
    Returns: ParlantEngine instance (or equivalent configured object)
    """
    pass
