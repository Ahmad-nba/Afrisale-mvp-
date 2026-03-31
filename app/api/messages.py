from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.schemas import WebhookPayload
from app.services.message_service import handle_inbound

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/webhook")
def webhook(body: WebhookPayload, db: Session = Depends(get_db)) -> dict:
    reply = handle_inbound(db, body.from_, body.text)
    return {"status": "ok", "reply": reply}
