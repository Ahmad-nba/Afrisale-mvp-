# Afrisale MVP — Project state (code-derived audit)

This document describes the **current state of the system** as verified from the repository. It is intended as a **handover + redesign foundation** (e.g. migration to Parlant). No LangGraph dependency or usage appears in `requirements.txt` or under `app/`.

---

## 1. System overview

**What the system does (from code)**

- Hosts a **FastAPI** app (`main.py`) that creates **SQLAlchemy** tables on startup (`Base.metadata.create_all`) and mounts a single router under the **`/api`** prefix.
- Exposes **HTTP endpoints** for health checks and **inbound messaging webhooks** (`app/api/messages.py`).
- For each accepted inbound message, it **persists the customer and messages**, optionally **blocks or rewrites** content via guardrails, runs **one Gemini call per turn** with **LangChain `StructuredTool`s** (`app/agents/agents.py` `run_turn`), then **sends an outbound reply** either via **Twilio WhatsApp** (when the caller supplies `outbound_send`) or via **Africa’s Talking SMS** (`app/services/message_service.py`, `app/integrations/*`).

**Core purpose**

- Conversational storefront backend: **catalog + orders in SQLite**, **owner vs customer** behavior distinguished by comparing inbound phone to `settings.owner_phone` (`message_service.handle_inbound`).

**Current capabilities**

- **Customer tools (LLM-bound):** list formatted catalog, create order, check order status (`app/agents/tools.py`).
- **Owner tools (LLM-bound):** add product, update stock/price, list orders (`app/agents/tools.py`).
- **Order creation** with stock check and decrement (`app/services/orders.py`).
- **Catalog search** (substring on name/description) exists in `app/services/catalog.py` **`search_products`** but is **not** exposed as an LLM tool in `tools.py` (only `get_products_formatted` is).
- A **separate, non-production** rule-based flow **`run_agent`** in `app/agents/agents.py` implements greeting/search/pick/qty/place-order using `search_products` and `create_order_service`; it is **only** wired from `test_agent.py`, not from the API.

---

## 2. Architecture breakdown

### Entry points

| Path | Handler | Notes |
|------|---------|--------|
| `GET /api/health` | `health()` | Returns `{"status": "ok"}` |
| `GET /api/webhook/health` | `test_webhook()` | Returns `{"message": "GET works"}` |
| `POST /api/webhook` | `webhook_json()` | JSON body `WebhookPayload`: `from` (alias), `text` |
| `POST /api/webhook/whatsapp` | `whatsapp_webhook()` | `application/x-www-form-urlencoded` (Twilio-style); reads `From`, `Body` |

`main.py` uses `prefix="/api"`; there is **no** route at `/health` without `/api`.

### Core modules

- **`app/api/messages.py`** — HTTP layer, Twilio form parsing, delegates to `handle_inbound`.
- **`app/services/message_service.py`** — customer/message persistence, guardrails, `run_turn`, outbound dispatch.
- **`app/agents/agents.py`** — `run_turn` (Gemini + tools), plus unused-in-production `run_agent` FSM.
- **`app/agents/prompt.py`** — system prompt strings.
- **`app/agents/tools.py`** — LangChain `StructuredTool` definitions.
- **`app/services/catalog.py`**, **`app/services/orders.py`** — business logic + DB.
- **`app/memory/memory_service.py`** — last N messages for prompt context.
- **`app/guardrails/*`** — inbound validation and outbound text filtering.
- **`app/core/config.py`**, **`app/core/database.py`** — settings and SQLite-friendly engine/session.

### Agent / LLM orchestration

- **LangChain Google GenAI** `ChatGoogleGenerativeAI` with **`bind_tools`**, single **`invoke`** (`run_turn`).
- **No** `langgraph` in `requirements.txt` and **no** LangGraph imports in `app/`.
- **At most one tool invocation per user message:** if `tool_calls` is non-empty, only **`tool_calls[0]`** is executed; the model is **not** called again with the tool result (`agents.py`).

### External integrations

- **Twilio** — outbound WhatsApp (`app/integrations/twilio_whatsapp.py`); inbound webhook field parsing in `messages.py`.
- **Africa’s Talking** — `httpx` POST to `settings.at_base_url` (`app/integrations/africastalking.py`); skipped or logged if `skip_sms_send` or missing credentials.

### Data storage

- **SQLAlchemy ORM** models: `Product`, `ProductVariant`, `Customer`, `Order`, `OrderItem`, `Message`, `CustomerEntity` (`app/models/models.py`).
- **`CustomerEntity`** is **defined** but **never referenced** elsewhere in application code (only `models.py` and a script duplicate in `scripts/_w2.py`).
- **SQLite** default `sqlite:///./afrisale.db` (`config.py`).

---

## 3. Request flow (critical)

### A. Message received — JSON webhook `POST /api/webhook`

1. **`webhook_json`** (`messages.py`) parses `WebhookPayload` → `from_`, `text`.
2. **`handle_inbound(db, from_, text)`** (`message_service.py`):
   - **`get_or_create_customer`** — normalize phone (`normalize_phone`), insert `Customer` if missing, `commit`.
   - **`input_guardrails.validate_inbound_message(text)`** — length, empty check, heuristic “intent”; on failure: **`save_message` in**, set `reply = detail`, **`save_message` out**, **`_deliver_outbound`** → **`africastalking.send_sms`** (no `outbound_send`), return.
   - **`role`** = `"owner"` if normalized `from_phone` equals normalized `settings.owner_phone`, else `"customer"`.
   - **`run_turn(db, role, customer.id, detail)`** — see section B.
   - **`output_guardrails.validate_assistant_text(db, raw_reply)`**.
   - **`save_message` out**, **`_deliver_outbound`** → SMS, return `safe_reply`.
3. **`webhook_json`** returns `{"status": "ok", "reply": reply}` — the reply text is **also** what was sent via SMS inside `handle_inbound`.

### A. Message received — Twilio WhatsApp `POST /api/webhook/whatsapp`

1. **`whatsapp_webhook`** reads `await request.form()`, logs/prints form keys.
2. **`From`** → **`_twilio_from_to_e164`** strips `whatsapp:` prefix, **`normalize_phone`**.
3. **`Body`** stripped.
4. **`handle_inbound(..., outbound_send=lambda to, msg: twilio_whatsapp.send_whatsapp(to, msg))`**.
5. Returns **`PlainTextResponse("OK", 200)`** — Twilio does **not** receive the assistant text in the HTTP response; the user gets the reply **only** via **`send_whatsapp`**.

### B. Response generated — `run_turn` (production path)

1. If **`settings.google_api_key`** is falsy → return fixed string: **`"Server misconfiguration: GOOGLE_API_KEY is not set."`** (config field is `google_api_key`; `.env.example` documents `GOOGLE_API_KEY`, which pydantic-settings typically maps).
2. **`catalog_service.get_products_formatted(db)`** — full catalog string.
3. **`get_recent_messages(db, customer_id, limit=5)`** then **`format_memory_for_prompt`** — chronological “User:/Assistant:” block.
4. **`prompt.build_system_prompt(role, products_snapshot, memory_block)`**.
5. **`tools.build_owner_tools(db)`** or **`tools.build_customer_tools(db, customer_id)`**.
6. Instantiate **`ChatGoogleGenerativeAI`**, **`bind_tools(tool_list)`**, **`invoke([SystemMessage, HumanMessage])`**.
7. If **`response.tool_calls`** present: take **first** call only; resolve tool by **name** in `tool_map`; **`chosen.invoke(args)`**; return **`str(out)`** (or error string on exception).
8. Else return **text** via **`_message_content_text(response.content)`**.

**Data transformations**

- Phone normalization; inbound text may be replaced by guardrail messages; assistant text may be **replaced entirely** by **`output_guardrails._FALLBACK`** based on regex scans for currency/numbers and product name heuristics (`output_guardrails.py`).

---

## 4. Current agent / conversation logic

**Production path**

- **LLM-driven** with **tool calling**, not a fixed dialog graph.
- **Conversation context** = **last 5 DB messages** for that `customer_id` (not full thread).
- **Prompt** instructs the model to call tools for actions and (for customers) to clarify size, color, delivery before confirming — but **delivery is not modeled** in `Order` / `Customer` tables; only **`Order` + `OrderItem`** and variant fields exist.

**Alternate path (`run_agent`)**

- **Rule-based** `detect_intent` + **in-memory `session_state`** (not persisted): greeting, product search via **`search_products`**, numeric pick, quantity, **`place_order`** via **`create_order_service`**.
- **`order_followup`** explicitly returns: *“Order follow-up is not wired in this harness yet.”*
- **`_ensure_customer_id`** forces orders onto **`HARNESS_CUSTOMER_PHONE = "+19995550333"`** in the DB for that harness — **not** the webhook user’s customer id.

**Prompts / chains / graphs**

- **Single system + human message** per turn; **no** LangChain chain composition beyond `bind_tools` + `invoke`.
- **No** LangGraph.

**Limitations (observable)**

- **One tool per message**; no agent loop to interpret tool output or chain tools.
- **`search_products`** is unused in `run_turn` / `tools.py` — product discovery in production depends on the model reading the **full formatted catalog** in the system prompt.
- **Owner and customer prompts** both appear in the customer branch of `build_system_prompt` (paragraph about “To the owner you are…” inside the non-owner return) — **copy/paste inconsistency** in `prompt.py`.

---

## 5. Implemented features (verified in code)

- **REST API** with health and webhook routes under **`/api`**.
- **Customer CRUD-by-phone** and **message logging** (`in` / `out`).
- **Inbound guardrails** (length + heuristics).
- **Outbound guardrails** (catalog-aligned text filtering).
- **Gemini + structured tools** for catalog read, order create/status (customer) and catalog write + order list (owner).
- **SQLite persistence** for products, variants, customers, orders, order lines, messages.
- **Stock and price enforcement** on order creation (`orders.create_order`).
- **WhatsApp outbound** via Twilio when webhook supplies the lambda.
- **SMS outbound** via Africa’s Talking when no `outbound_send` (JSON webhook path).
- **Dev/scripts:** `scripts/agentTest.py` mirrors production path (`run_turn` + guardrails + DB messages); `scripts/agent_test.py` smoke-tests `run_turn`; `test_agent.py` exercises **`run_agent`** only.

---

## 6. Partially implemented / fragile areas

- **`run_agent` / `test_agent.py` vs production:** Two different brains; harness uses a **fixed phone** for orders and **stub** order follow-up.
- **`run_turn` single-tool:** Multiple or sequential tool needs fail silently beyond the first call.
- **`output_guardrails.validate_assistant_text`:** Any assistant reply mentioning **prices not exactly matching** a variant price in DB, or certain marketing phrases **without** a substring match of a product name (length ≥ 3), can be **replaced** with a generic fallback — can **clash** with valid LLM answers (e.g. shipping estimates, conversational text with numbers).
- **Twilio path:** **`print` debugging** in production webhook (`messages.py`); **`send_whatsapp`** swallows failures after logging — caller still returns **OK**.
- **Africa’s Talking:** On HTTP ≥400, only **logs**; no retry or surfaced error to the user in-app.
- **`README.md` paths** say `GET /health` and `POST /webhook` — **actual** routes are **`/api/health`** and **`/api/webhook`** (documentation drift).
- **`CustomerEntity` table:** **No** read/write code in `app/`.
- **Owner role:** If **`OWNER_PHONE`** unset, **`normalize_phone("")`** comparison yields **everyone treated as customer** (no explicit “unknown owner” handling).

---

## 7. Missing but expected (from structure / prompts only)

- **Persisted conversation/session state** for a structured checkout FSM (production uses only LLM + 5 messages).
- **Use of `search_products` in the live agent** (implemented in `catalog.py`, not in `tools.py`).
- **Delivery / address fields** in the schema despite prompt asking for delivery location.
- **Multi-step tool orchestration** (plan → act → observe → reply).
- **Webhook verification / auth** for Twilio or Africa’s Talking (not present in `messages.py`).
- **`app` package has no `__init__.py` files** in the tree found — relies on **namespace package** layout; works when run from repo root but is **atypical** for packaging/deployment.

---

## 8. Technical debt / risks

- **Tight coupling:** `handle_inbound` owns persistence, guardrails, agent, and transport.
- **Dual agent implementations** (`run_turn` vs `run_agent`) increase **confusion and maintenance risk**.
- **Scaling:** SQLite, synchronous DB session per request, single LLM call blocking the request path.
- **Debugging:** `print` in webhook; Twilio returns **OK** regardless of downstream send/agent failures (partially mitigated by logging in `handle_inbound` for `run_turn`).
- **Security:** No signature validation on webhooks; inbound content only lightly filtered.
- **Output guardrails** may **mask model bugs** by substituting canned text, making **production failures hard to diagnose** from user-visible text alone.

---

## 9. Readiness for Parlant migration

**Can often stay as-is (boundary layers)**

- **FastAPI routes** and **webhook parsing** (`messages.py`) as the **ingress adapter**.
- **SQLAlchemy models** and **catalog/order services** as **domain + persistence** (subject to whether Parlant expects different tool contracts).
- **Twilio / Africa’s Talking** modules as **outbound channels** (same idea: pluggable `outbound_send`).

**Likely replaced or heavily reworked**

- **`run_turn`** as the **sole “brain”** (single `invoke`, first tool only) — a Parlant-style agent would **own** turn-taking, policies, and **multi-step** tool use.
- **`prompt.build_system_prompt` + manual memory block** — typically becomes **managed prompts / policies** in the new framework.
- **`input_guardrails` / `output_guardrails`** — may map to Parlant guardrails or need **redesign** so they do not fight the new runtime.

**Refactor before / during integration**

- **Unify** on one conversation architecture; **remove or clearly quarantine `run_agent`** if Parlant subsumes it.
- **Expose `search_products` (or DB query tools)** explicitly if you want **scalable catalog** without huge system prompts.
- **Decouple** `handle_inbound` into: **normalize → persist inbound → call agent runtime → persist outbound → send** — eases swapping the middle.
- **Align schema with prompts** (e.g. delivery) or **narrow prompts** to what the DB supports.
- **Fix README / OpenAPI** so operators hit **`/api/...`** paths.

---

## Summary

The live system is a **thin FastAPI layer** around **SQLite + one-shot Gemini tool calling** and **optional SMS/WhatsApp**. There is **no LangGraph**. A **second, rule-based agent** exists for **local CLI testing only** and **does not** match the webhook path. For redesign, treat **`run_turn` + `tools.py` + `message_service.handle_inbound`** as the **actual** runtime, and **`run_agent`** as **non-production** unless explicitly wired in.
