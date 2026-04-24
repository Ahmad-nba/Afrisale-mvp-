# Afrisale MVP: Current User Flow and Media Expansion Plan

## Audience and Purpose

This document is written for project architects and product engineers.
It explains how the system currently works in production-like flow (text-first chat), then proposes a concrete engineering path to support image and video messaging while preserving the existing agentic workflow.

The goal is to align on architecture decisions before implementation.

## Current System at a Glance

- API surface:
  - `POST /api/webhook` (JSON payload for SMS-like channels)
  - `POST /api/webhook/whatsapp` (Twilio WhatsApp form payload)
- Core runtime:
  - `run_pipeline()` orchestrates inbound normalization, persistence, guardrails, agent turn, outbound formatting, and dispatch.
- Agent execution model:
  - One planner + one final generation per user turn (with optional tool call in between) via `LocalParlantEngine` fallback.
  - LLM provider is now Vertex AI (GCP) through Gemini.
- Persistence:
  - SQLite via SQLAlchemy models (`Customer`, `Message`, `ConversationState`, `Order`, `OrderItem`, `Product`, `ProductVariant`).
- Channel outputs:
  - SMS via Africa's Talking
  - WhatsApp via Twilio text messages

## End-to-End User Flow (Current)

### 1) Inbound request handling

`app/api/messages.py` receives inbound payloads:

- JSON webhook uses `WebhookPayload(from, text)`.
- WhatsApp webhook reads form fields:
  - sender from `From`
  - text from `Body`

Both paths call:

`run_pipeline(db, from_raw, text_raw, owner_phone, outbound_send=...)`

### 2) Pipeline orchestration

`app/pipeline/runner.py` executes this order:

1. Normalize inbound (`stages.normalize_inbound`)
2. Persist inbound (`stages.persist_inbound`)
3. Input guardrail (`InputGuardrail.validate`)
4. Role resolution (`owner` vs `customer`)
5. Agent invocation (`stages.call_agent`)
6. Output validation guardrail (`OutputValidationGuardrail.validate`)
7. Output formatting (`OutputFormattingGuardrail.format`)
8. Persist outbound (`stages.persist_outbound`)
9. Dispatch outbound (`stages.dispatch_outbound`)

This means all user-visible replies are stored, validated, formatted, then sent.

### 3) Session and memory behavior

`app/parlant_agent/session.py` assembles the per-turn context:

- Loads recent message history (last 6 messages from `messages` table).
- Loads structured memory state from `conversation_states`.
- Builds role-specific tools and guidelines.
- Binds DB-aware tool handlers.
- Calls engine `run_turn`.

### 4) Engine behavior per turn

`app/parlant_agent/engine.py` (`LocalParlantEngine`) uses:

- Planner prompt:
  - decides whether tool call is needed
  - returns JSON `{"tool": ..., "args": ...}`
- Optional tool execution:
  - executes mapped handler
  - updates structured memory via `derive_memory_update`
- Final prompt:
  - includes role, guidelines, recent history, memory slots, and tool result
  - generates final assistant reply

Retry policy is configurable (`llm_retry_attempts`, `llm_retry_backoff_seconds`, timeout).

### 5) LLM inference stack (current)

- Provider: `GeminiProvider`
- Client: `google.genai.Client(vertexai=True, project=..., location=...)`
- Auth: ADC (`GOOGLE_APPLICATION_CREDENTIALS` or gcloud ADC)
- Model selection: `GCP_MODEL` (fallback to `GEMINI_MODEL`)

This migration only changed inference transport/auth. Agent logic and tool flow remained intact.

## Database Structure and Access Patterns

## Primary tables

- `customers`
  - identity key is `phone_number` (unique)
- `messages`
  - `customer_id`, `message`, `direction` (`in`/`out`)
  - stores plain text only today
- `conversation_states`
  - one row per customer (`customer_id` unique), JSON blob in `state_json`
- `products`, `product_variants`
  - catalog + purchasable variants
- `orders`, `order_items`
  - order ledger

## Data access ownership

- `message_service`
  - normalize phone
  - get/create customer
  - save/get messages
- `conversation_state_service`
  - load/save structured memory JSON
- `catalog` and `orders` services
  - all product/order write and read logic
- `tool_registry`
  - wraps service methods into tool handlers for the agent

This separation is clean for extension: media support can be added with minimal impact if we keep service-layer boundaries.

## Current Memory Model (What the Agent Remembers)

`conversation_states.state_json` currently tracks:

- `lastProductCandidates`
- `selectedProductId`
- `selectedVariantId`
- `lastMentionedPrice`
- `deliveryLocation`

How memory is used now:

- heuristic extraction from user text (price, delivery location)
- tool result to memory projection (`derive_memory_update`)
- memory stitched into prompts every turn

Important: memory is text/catalog/order oriented. There is no media memory (e.g., "last sent image", "attachment intent", "proof-of-payment image").

## Guardrails and Channel Constraints (Current)

- Input guardrail expects meaningful alphabetic text.
- Output validation checks hallucinated prices and suspicious product names.
- Output formatting enforces text limits:
  - WhatsApp ~1600 chars
  - SMS ~160 chars

Current implementation assumes text payloads and text replies.
No media-specific validation, moderation, storage, or dispatch logic exists.

## What Is Missing for Image/Video Messaging

To support sending/receiving media, the system needs first-class handling in four layers:

1. **Ingress parsing**
   - Twilio inbound fields like `NumMedia`, `MediaUrl0...`, `MediaContentType0...` are currently ignored.
2. **Persistence model**
   - `messages` has only one text column; no attachment metadata or media lifecycle status.
3. **Agent context and tools**
   - agent cannot reason over media metadata or trigger media-send actions.
4. **Egress transport**
   - Twilio outbound currently sends text only (`body` without `media_url`).

## Recommended Target Architecture for Media

## 1) Data model changes (minimum viable, production-safe)

Introduce an attachment table rather than overloading `messages`:

- `message_attachments`
  - `id`
  - `message_id` (FK -> `messages.id`)
  - `direction` (`in`/`out`) optional if always inherited from message
  - `kind` (`image`, `video`, `audio`, `document`, `other`)
  - `mime_type`
  - `provider` (`twilio`, `africastalking`, `internal`)
  - `provider_media_id` (nullable)
  - `source_url` (original provider URL, short-lived)
  - `storage_url` (durable object storage URL or key)
  - `checksum` (optional)
  - `bytes_size` (optional)
  - `caption` (optional)
  - `created_at`

Recommended companion columns on `messages`:

- `channel` (`sms`, `whatsapp`, future channels)
- `message_type` (`text`, `media`, `mixed`, `system`)

Why separate table:

- supports many attachments per message
- keeps text path backward compatible
- allows async media fetch/transcode/moderation workflows

## 2) Inbound pipeline changes

Add a normalized inbound envelope object (instead of raw text-only tuple):

- `sender_phone`
- `text`
- `channel`
- `attachments[]` (each with URL + MIME + provider ids)

Apply this in:

- `api/messages.py` (Twilio parser for media fields)
- `pipeline/stages.normalize_inbound` (return rich payload)
- `persist_inbound` (save message + attachments transactionally)

## 3) Agent context and memory extension

Keep existing turn mechanics unchanged, but enrich inputs:

- include attachment summary in prompt context:
  - example: "User attached 1 image (image/jpeg)."
- extend structured memory with media-aware slots:
  - `lastInboundAttachments`
  - `lastAttachmentIntent` (e.g., product inquiry, payment proof)
  - `lastResolvedMediaEntity` (optional)

This preserves the current planner/tool/final-response loop while allowing media-aware reasoning.

## 4) Tooling extensions (without breaking current tools)

Add optional tools, not replacements:

- `inspect_recent_attachments(customer_id, limit)`
- `attach_media_to_reply(url, mime_type, caption?)` (if using staged send flow)
- `create_order_from_reference_image(...)` (future, optional)

Keep existing catalog/order tools intact to avoid regressions.

## 5) Outbound dispatch updates

Enhance transport adapters:

- Twilio:
  - support `messages.create(..., media_url=[...])` for WhatsApp
- Africa's Talking SMS:
  - remain text-only fallback (or include link only)

Dispatch contract should accept:

- text body
- zero or more media descriptors

If target channel cannot carry media, degrade gracefully:

- send text with hosted URL
- log capability downgrade

## 6) Storage and security model

For production reliability, do not depend on ephemeral provider URLs alone.
Add media ingestion worker/process:

1. validate MIME/size
2. optional malware/content checks
3. copy to durable storage bucket
4. store normalized metadata in `message_attachments`

This is required for:

- replayability
- auditability
- long-term training/analytics
- resilient retrieval for support workflows

## API Contract Evolution (Suggested)

## Inbound internal contract

Move from:

- `(from_raw, text_raw)`

to:

- `InboundMessageEvent`
  - `sender`
  - `channel`
  - `text`
  - `attachments`
  - `provider_payload` (optional raw snapshot)

## Outbound internal contract

Move from:

- `dispatch_outbound(to, reply, outbound_send)`

to:

- `dispatch_outbound(event: OutboundMessageEvent)`
  - `to`
  - `channel`
  - `text`
  - `attachments`
  - `fallback_policy`

This gives one place for channel capability logic.

## Migration Plan (Low-Risk Sequence)

## Phase 1: Schema and plumbing

- add `message_attachments` table
- add `channel`/`message_type` columns to `messages`
- keep existing text flow unchanged

## Phase 2: Inbound media capture

- parse Twilio media fields
- persist attachments with inbound message
- no agent behavior change yet

## Phase 3: Outbound media send path

- extend dispatch contract and Twilio adapter
- enable manual/explicit media reply from code paths

## Phase 4: Agent media awareness

- add attachment summaries to prompt context
- add memory slots for media references
- introduce optional media tools

## Phase 5: Hardening

- durable storage ingestion
- moderation policy and limits
- observability dashboards and retries for media jobs

## Risks and Design Decisions to Resolve

- **Storage strategy:** provider URL passthrough vs durable object storage (recommended: durable storage).
- **Compliance/security:** retention, PII handling, media moderation policy.
- **Channel parity:** WhatsApp can carry media; SMS cannot.
- **Cost controls:** media egress/storage/transcoding limits.
- **Agent scope:** whether to do vision inference now or keep V1 as metadata-aware only.

## Immediate Next Steps for Team Discussion

1. Approve target schema (`message_attachments` + message metadata fields).
2. Approve normalized inbound/outbound event contracts.
3. Decide V1 scope:
   - receive + persist media only
   - or receive + persist + outbound media send
4. Decide storage and security baseline (bucket, retention, moderation).
5. Create implementation tickets by phase above.

---

If the team wants, this can be converted into a technical RFC with:

- SQL migrations
- sequence diagrams
- endpoint contract examples
- rollout/rollback plan
- test matrix (unit/integration/channel sandbox)
