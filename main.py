"""
Single FastAPI application entrypoint. Run: uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import app.models.models  # noqa: F401 — register ORM models before create_all

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.messages import router as messages_router
from app.api.seller import router as seller_router
from app.core.config import settings
from app.core.database import Base, engine
from app.core.migrations import ensure_schema
from app.services import seller_notification

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)
ensure_schema(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Boots the seller-notification background loop on startup and cancels it
    cleanly on shutdown so we don't leak the asyncio task during dev reloads.
    """
    task = None
    try:
        task = seller_notification.start_background_loop()
    except Exception:
        logger.exception("seller_notification_loop_start_failed")
        task = None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except Exception:
                pass


app = FastAPI(title="Afrisale MVP", lifespan=lifespan)


def _build_cors_origins() -> list[str]:
    origins: list[str] = []
    base_url = (settings.seller_base_url or "").strip().rstrip("/")
    if base_url:
        origins.append(base_url)
    # Always allow local Next.js dev so engineers can `npm run dev` against a
    # remotely-deployed backend without flipping config.
    for fallback in ("http://localhost:3000", "http://127.0.0.1:3000"):
        if fallback not in origins:
            origins.append(fallback)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(messages_router, prefix="/api")
app.include_router(seller_router)
