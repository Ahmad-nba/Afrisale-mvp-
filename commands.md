### Start app
uvicorn main:app --reload

###Tunneling command (cloudflare)
cloudflared tunnel --url http://localhost:8000

###curl testing of the tunneler:
curl -X POST https://<tunnel>/api/webhook \
  -H "Content-Type: application/json" \
  -d '{"from_": "+256700000000", "text": "hello"}'