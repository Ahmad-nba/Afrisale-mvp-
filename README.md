# Afrisale MVP

Single-business conversational commerce backend: FastAPI + SQLite + Gemini 2.5 Flash (one LLM call per message) + Africa’s Talking SMS.

## Setup

1. Create a virtual environment and install dependencies (from the project root):

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Copy environment template and edit values:

```bash
copy .env.example .env
```

Set at least `GCP_PROJECT_ID` and `OWNER_PHONE`. Ensure ADC auth is configured (`GOOGLE_APPLICATION_CREDENTIALS` or `gcloud auth application-default login`). For local runs without sending SMS, set `SKIP_SMS_SEND=true`.

3. Run the API (must be run from the repo root so `sqlite:///./afrisale.db` resolves):

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- Health: `GET http://localhost:8000/api/health`
- Webhook (JSON): `POST http://localhost:8000/api/webhook` with JSON body `{"from": "+2567XXXXXXX", "text": "hello"}`
- WhatsApp webhook: `POST http://localhost:8000/api/webhook/whatsapp`

## Scripts

| Script | Purpose |
|--------|---------|
| [`scripts/database_read_write_test.py`](scripts/database_read_write_test.py) | DB + memory_service checks (no LLM auth needed) |
| [`scripts/seed_test_products.py`](scripts/seed_test_products.py) | Inserts two sample products into local SQLite (idempotent) |
| [`scripts/read_local_db_catalog.py`](scripts/read_local_db_catalog.py) | Prints catalog from `DATABASE_URL` (no Gemini) |
| [`scripts/agentTest.py`](scripts/agentTest.py) | Interactive chat: ask for products; agent uses tools against local DB (needs `GCP_PROJECT_ID` + ADC) |
| [`scripts/agent_test.py`](scripts/agent_test.py) | One Gemini turn (needs `GCP_PROJECT_ID` + ADC) |
| [`scripts/_w.py`](scripts/_w.py) … [`scripts/_w10.py`](scripts/_w10.py) | Historical scaffold writers that generated early files; **re-running overwrites targets** — see [`scripts/README.md`](scripts/README.md) |

Run feature tests from the repo root:

```bash
python scripts/seed_test_products.py
python scripts/read_local_db_catalog.py
python scripts/database_read_write_test.py
python scripts/agentTest.py
python scripts/agent_test.py
```

## Layout

Application code lives under [`app/`](app/). Entry point is [`main.py`](main.py).
