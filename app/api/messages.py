import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.integrations import twilio_whatsapp
from app.schemas.schemas import WebhookPayload
from app.services.message_service import handle_inbound, normalize_phone

logger = logging.getLogger(__name__)

router = APIRouter()


def _twilio_from_to_e164(from_field: str | None) -> str:
    s = (from_field or "").strip()
    prefix = "whatsapp:"
    if s.lower().startswith(prefix):
        s = s[len(prefix) :]
    return normalize_phone(s)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}

@router.get("/webhook/health")
def test_webhook():
    return {"message": "GET works"}

@router.post("/webhook")
def webhook_json(body: WebhookPayload, db: Session = Depends(get_db)) -> dict:
    """JSON webhook (e.g. Africa's Talking style)."""
    reply = handle_inbound(db, body.from_, body.text)
    return {"status": "ok", "reply": reply}


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)) -> PlainTextResponse:
    """
    Twilio inbound WhatsApp: application/x-www-form-urlencoded.
    Full URL: https://<host>/api/webhook/whatsapp
    """
    data = await request.form()
    form_snapshot = {key: data.get(key) for key in data.keys()}

    print("🔥 WEBHOOK CALLED 🔥")
    print(form_snapshot)
    logger.info("whatsapp_webhook form keys=%s", list(form_snapshot.keys()))

    from_raw = data.get("From")
    body = (data.get("Body") or "").strip()
    from_phone = _twilio_from_to_e164(str(from_raw) if from_raw is not None else "")

    reply = handle_inbound(
        db,
        from_phone,
        body,
        outbound_send=lambda to, msg: twilio_whatsapp.send_whatsapp(to, msg),
    )
    logger.info("whatsapp_webhook reply_len=%s", len(reply))
    return PlainTextResponse("OK", status_code=200)
