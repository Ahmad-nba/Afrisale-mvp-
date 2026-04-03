"""
Single FastAPI application entrypoint. Run: uvicorn main:app --reload --port 8000
"""
import app.models.models  # noqa: F401 — register ORM models before create_all

from fastapi import FastAPI

from app.api.messages import router
from app.core.database import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Afrisale MVP")
app.include_router(router, prefix="/api")
