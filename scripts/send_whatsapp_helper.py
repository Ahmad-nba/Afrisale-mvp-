from twilio.rest import Client
import os
from dotenv import load_dotenv
load_dotenv()

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_whatsapp_number = os.getenv("TWILIO_WHATSAPP_NUMBER")

client = Client(account_sid, auth_token)

def send_whatsapp(to, message):
    client.messages.create(
        from_='whatsapp:+14155238886',  # Twilio sandbox number
        body=message,
        to=f'whatsapp:{to}'
    )