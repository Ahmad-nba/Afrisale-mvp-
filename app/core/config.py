from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./afrisale.db"
    google_api_key: str = "GOOGLE_API_KEY"
    owner_phone: str = ""

    at_username: str = ""
    at_api_key: str = ""
    at_sender_id: str = ""
    at_base_url: str = "https://api.africastalking.com/version1/messaging"

    gemini_model: str = "gemini-2.5-flash"

    skip_sms_send: bool = False


settings = Settings()
