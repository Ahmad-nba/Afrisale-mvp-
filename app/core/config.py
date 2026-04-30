from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./afrisale.db"
    google_api_key: str = ""
    gcp_project_id: str = ""
    gcp_location: str = "us-central1"
    gcp_model: str = "gemini-2.5-flash"
    google_application_credentials: str = ""
    owner_phone: str = ""

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"

    at_username: str = ""
    at_api_key: str = ""
    at_sender_id: str = ""
    at_base_url: str = "https://api.africastalking.com/version1/messaging"

    gemini_model: str = "gemini-2.5-flash"
    llm_timeout_seconds: float = 30.0
    llm_retry_attempts: int = 3
    llm_retry_backoff_seconds: float = 0.8

    skip_sms_send: bool = False

    gcs_bucket_products: str = ""
    gcs_signed_url_ttl_seconds: int = 60 * 60 * 24

    vertex_vector_index_id: str = ""
    vertex_vector_index_endpoint_id: str = ""
    vertex_vector_deployed_index_id: str = ""
    vertex_vector_dimensions: int = 1408
    vertex_embedding_model: str = "multimodalembedding@001"

    image_max_bytes: int = 10 * 1024 * 1024
    image_allowed_mimes: str = "image/jpeg,image/png,image/webp,image/heic,image/heif"

    # Cross-modal cosine (text query -> image vector) is systematically lower
    # than image-to-image cosine in this multimodal embedding model, so we
    # use two thresholds. Tune empirically; defaults below are calibrated
    # against the seeded MVP catalog.
    image_match_min_similarity: float = 0.30  # legacy/default; image-mode threshold
    image_match_min_similarity_image: float = 0.30
    image_match_min_similarity_text: float = 0.06
    image_match_top_k: int = 4


settings = Settings()
