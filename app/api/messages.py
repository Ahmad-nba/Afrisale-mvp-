import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.integrations import twilio_whatsapp
from app.pipeline.runner import run_pipeline
from app.schemas.schemas import WebhookPayload

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}

@router.get("/webhook/health")
def test_webhook():
    return {"message": "GET works"}

@router.post("/webhook")
async def webhook_json(payload: WebhookPayload, db: Session = Depends(get_db)) -> dict:
    """JSON webhook (e.g. Africa's Talking style)."""
    reply = await run_pipeline(
        db=db,
        from_raw=payload.from_,
        text_raw=payload.text,
        owner_phone=settings.owner_phone,
        outbound_send=None,
    )
    return {"status": "ok", "reply": reply}


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)) -> PlainTextResponse:
    """
    Twilio inbound WhatsApp: application/x-www-form-urlencoded.
    Full URL: https://<host>/api/webhook/whatsapp
    """
    form = await request.form()
    form_snapshot = {key: form.get(key) for key in form.keys()}

    print("🔥 WEBHOOK CALLED 🔥")
    print(form_snapshot)
    logger.info("whatsapp_webhook form keys=%s", list(form_snapshot.keys()))

    reply = await run_pipeline(
        db=db,
        from_raw=str(form.get("From", "")),
        text_raw=str(form.get("Body", "")).strip(),
        owner_phone=settings.owner_phone,
        outbound_send=lambda to, msg: twilio_whatsapp.send_whatsapp(to, msg),
    )
    logger.info("whatsapp_webhook reply_len=%s", len(reply))
    return PlainTextResponse("OK", status_code=200)
