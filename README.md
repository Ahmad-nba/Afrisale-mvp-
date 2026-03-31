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

Set at least `GOOGLE_API_KEY` and `OWNER_PHONE`. For local runs without sending SMS, set `SKIP_SMS_SEND=true`.

3. Run the API (must be run from the repo root so `sqlite:///./afrisale.db` resolves):

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- Health: `GET http://localhost:8000/health`
- Webhook: `POST http://localhost:8000/webhook` with JSON body `{"from": "+2567XXXXXXX", "text": "hello"}`

## Scripts

| Script | Purpose |
|--------|---------|
| [`scripts/database_read_write_test.py`](scripts/database_read_write_test.py) | DB + memory_service checks (no API key) |
| [`scripts/agent_test.py`](scripts/agent_test.py) | One Gemini turn (needs `GOOGLE_API_KEY`) |
| [`scripts/_w.py`](scripts/_w.py) … [`scripts/_w10.py`](scripts/_w10.py) | Historical scaffold writers that generated early files; **re-running overwrites targets** — see [`scripts/README.md`](scripts/README.md) |

Run feature tests from the repo root:

```bash
python scripts/database_read_write_test.py
python scripts/agent_test.py
```

## Layout

Application code lives under [`app/`](app/). Entry point is [`main.py`](main.py).
