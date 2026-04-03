# Twilio WhatsApp webhook — verification checklist

## Exact URL (Twilio console)

Configure **When a message comes in** with:

- **URL:** `https://<your-tunnel-host>/api/webhook/whatsapp`
- **Method:** `HTTP POST`
- No trailing slash unless your tunnel adds one consistently.

Common mistake: omitting `/api` (router prefix) or using `/webhook/whatsapp` only.

## HTTPS

Twilio requires a **public HTTPS** URL. Localhost must be exposed via **Pinggy, ngrok, Cloudflare Tunnel**, etc., and Twilio must point at the **https** forwarding URL.

## Sandbox

- Join the Twilio WhatsApp sandbox from your phone using the join code Twilio shows.
- Inbound messages must come from a number that has joined the sandbox (until you use a production WhatsApp sender).

## Server

- Start the API from the **project root** so imports resolve:

  `uvicorn main:app --host 0.0.0.0 --port 8000`

- If your tunnel forwards to another port, match that port in the tunnel config.

## Tunnel

- Tunnel process must be **running** and show requests when you hit the URL.
- Some tunnels give a new URL each run — update Twilio after each change.

## Environment (`.env`)

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- Optional: `TWILIO_WHATSAPP_FROM` (default `whatsapp:+14155238886` for sandbox)

Pydantic loads `.env` from the current working directory when the app starts.

## Expected logs when a message arrives

You should see in the server console:

```text
🔥 WEBHOOK CALLED 🔥
{'From': 'whatsapp:+1...', 'Body': '...', ...}
```

Then normal app logs for DB/agent if applicable.

## Quick manual POST test

Replace URL and form values as needed:

```bash
curl -X POST "https://<tunnel>/api/webhook/whatsapp" ^
  -H "Content-Type: application/x-www-form-urlencoded" ^
  -d "From=whatsapp%%2B15551234567&Body=hello"
```

(Use proper URL-encoding for `+` in phone numbers in curl.)
