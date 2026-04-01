# from fastapi import FastAPI, Request
# from send_whatsapp_helper import send_whatsapp

# import os
# from dotenv import load_dotenv
# load_dotenv()

# account_sid = os.getenv("TWILIO_ACCOUNT_SID")
# auth_token = os.getenv("TWILIO_AUTH_TOKEN")
# twilio_whatsapp_number = os.getenv("TWILIO_WHATSAPP_NUMBER")

# app = FastAPI()

# @app.post("/api/webhook/whatsapp")
# async def whatsapp_webhook(request: Request):
#     data = await request.form()

#     user_number = data.get("From")  # whatsapp:+256...
#     message = data.get("Body")

#     print("User:", user_number)
#     print("Message:", message)

#     send_whatsapp(
#         to=user_number.replace("whatsapp:", ""),
#         message="Got your message 👌"
#     )

#     return "OK"