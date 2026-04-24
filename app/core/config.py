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


settings = Settings()
