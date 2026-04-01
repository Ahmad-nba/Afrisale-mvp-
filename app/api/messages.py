from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.schemas import WebhookPayload
from app.services.message_service import handle_inbound
from scripts.send_whatsapp_helper import send_whatsapp

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/webhook")
def webhook(body: WebhookPayload, db: Session = Depends(get_db)):
    reply = handle_inbound(db, body.from_, body.text)
    return {"status": "ok", "reply": reply}

# @router.get("/webhook/whatsapp")
# def whatsapp_webhook_test():
#     return {"status": "ok"}

@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    data = await request.form()

    user_number = data.get("From")
    message = data.get("Body")

    print("🔥 HIT WEBHOOK 🔥")
    print("User:", user_number)
    print("Message:", message)

    send_whatsapp(
        to=user_number.replace("whatsapp:", ""),
        message="Got your message 👌"
    )

    return "OK"