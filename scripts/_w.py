import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def w(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip("\n") + "\n", encoding="utf-8")

w("app/__init__.py", "")
w("app/core/__init__.py", "")
w("app/core/config.py", '''
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./afrisale.db"
    google_api_key: str = ""
    owner_phone: str = ""

    at_username: str = ""
    at_api_key: str = ""
    at_sender_id: str = ""
    at_base_url: str = "https://api.africastalking.com/version1/messaging"

    gemini_model: str = "gemini-2.5-flash"

    skip_sms_send: bool = False


settings = Settings()
''')
w("app/core/database.py", '''
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
''')
print("ok1")
