# Parlant Conversational Flow + WhatsApp Webhook Integration Guide

## Purpose

This guide explains how Afrisale uses a Parlant-style agent layer to manage conversational flow and how that layer connects to the WhatsApp webhook. It is written so the same pattern can be reused in another project.

The core idea is:

1. WhatsApp receives the user message.
2. The API normalizes and persists it.
3. A conversation session loads memory, tools, and guidelines.
4. The agent decides whether to call a tool.
5. The final response is validated, formatted, persisted, and sent back to WhatsApp.

## Important Note About This Project's Parlant Usage

The code is structured around a Parlant-style session/runtime boundary, but it also includes a local fallback engine (`LocalParlantEngine`) that implements the same practical shape:

- role-specific guidelines
- tool registry
- recent conversation history
- structured memory
- planner step
- optional tool execution
- final response generation

In `build_engine()`, the code tries to instantiate Parlant's `Engine`. If that fails, it falls back to `LocalParlantEngine`.

This means the architecture pattern is portable even if the exact Parlant package behavior differs in another project.

## Main Files

- `app/api/messages.py`
  - FastAPI webhook routes.
- `app/pipeline/runner.py`
  - Full inbound-to-outbound pipeline.
- `app/pipeline/stages.py`
  - Small pipeline operations: normalize, persist, call agent, dispatch.
- `app/parlant_agent/session.py`
  - Conversation session wrapper.
- `app/parlant_agent/engine.py`
  - Parlant engine builder and local engine fallback.
- `app/parlant_agent/guidelines.py`
  - Role-specific behavioral instructions.
- `app/parlant_agent/tool_registry.py`
  - Tools available to the agent.
- `app/parlant_agent/providers/gemini_provider.py`
  - Gemini/Vertex AI inference provider.
- `app/integrations/twilio_whatsapp.py`
  - Outbound WhatsApp sender.

## WhatsApp Webhook Entry Point

The WhatsApp webhook lives in `app/api/messages.py`:

```python
@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)) -> PlainTextResponse:
    form = await request.form()

    reply = await run_pipeline(
        db=db,
        from_raw=str(form.get("From", "")),
        text_raw=str(form.get("Body", "")).strip(),
        owner_phone=settings.owner_phone,
        outbound_send=lambda to, msg: twilio_whatsapp.send_whatsapp(to, msg),
    )
    return PlainTextResponse("OK", status_code=200)
```

Twilio sends inbound WhatsApp messages as form data.

Current fields used:

- `From`: sender address, usually `whatsapp:+...`
- `Body`: text message body

The webhook does not directly run the agent. It delegates to `run_pipeline()` and passes an `outbound_send` callback for WhatsApp delivery.

This keeps channel-specific code at the edge.

## Pipeline Flow

`run_pipeline()` is the main orchestration function:

```python
async def run_pipeline(
    db,
    from_raw: str,
    text_raw: str,
    owner_phone: str,
    outbound_send: Callable[[str, str], None] | None = None,
) -> str:
```

The pipeline does the following:

1. Normalize sender and text.
2. Persist inbound message.
3. Run input guardrail.
4. Detect user role (`owner` or `customer`).
5. Call the agent session.
6. Validate the agent response.
7. Format response for WhatsApp or SMS.
8. Persist outbound message.
9. Send outbound message.

This design is useful because the webhook remains simple and the pipeline becomes reusable across channels.

## Role Selection

The system supports two roles:

- `owner`
- `customer`

Role is selected by comparing the inbound phone number with `OWNER_PHONE`:

```python
role = "owner" if phone == stages.normalize_phone(owner_phone) else "customer"
```

This role controls:

- which guidelines are loaded
- which tools are exposed
- how the assistant behaves

In another project, role selection can be replaced with account lookup, tenant membership, admin permissions, or workspace roles.

## Conversation Session Layer

`AfrisaleSession` is the boundary between app code and the agent runtime.

```python
new_session = AfrisaleSession(customer_id=customer.id, role=role)
reply = await new_session.run_turn(db, user_text=text)
```

The session owns conversation context assembly only. It does not own domain data directly.

Inside `AfrisaleSession.run()`:

1. Load guidelines by role.
2. Build tools by role.
3. Load recent messages from DB.
4. Load structured memory from DB.
5. Bind DB into tool handlers.
6. Build the engine.
7. Pass memory context into the engine.
8. Run the turn.

This gives the agent enough context without letting the LLM directly access the database.

## Guidelines

Guidelines are role-specific behavior instructions.

Customer guidelines include:

- help customers browse/search/place orders
- always confirm delivery location before order
- only quote prices from the catalog
- use `search_products` before reciting the catalog
- keep WhatsApp-friendly concise responses

Owner guidelines include:

- manage catalog
- update stock and prices
- list orders
- avoid exposing unnecessary customer details

In another project, guidelines should be treated as product policy plus UX tone.

## Tools

Tools are declared in `tool_registry.py`.

Each tool has:

- `name`
- `description`
- JSON-like `parameters`
- Python `handler`

Customer tools:

- `get_catalog`
- `search_products`
- `create_order`
- `get_order_status`

Owner tools:

- `add_product`
- `update_stock`
- `update_price`
- `list_all_orders`

The tool handlers call normal service-layer functions such as `catalog.search_products()` or `orders.create_order()`.

This is the key pattern to reuse:

- keep business logic in services
- expose only controlled actions as tools
- let the agent choose tools, but not bypass application logic

## Memory and Conversation History

The agent receives two forms of memory:

### Recent text history

Loaded from the `messages` table:

```python
recent_rows = message_service.get_recent_messages(db, self.customer_id, limit=6)
```

This creates short-term conversational continuity.

### Structured memory

Loaded from `conversation_states.state_json`.

Current memory fields:

- `lastProductCandidates`
- `selectedProductId`
- `selectedVariantId`
- `lastMentionedPrice`
- `deliveryLocation`

Structured memory is updated after tool calls using:

```python
derive_memory_update(selected_tool, args, tool_result)
```

This helps the assistant handle follow-ups like:

- "the black one"
- "send it to Kampala"
- "how much was that one?"

## Engine Prompt Flow

The local engine uses two LLM passes.

### 1) Planner pass

The planner prompt includes:

- role
- guidelines
- recent history
- structured memory
- available tools
- current user message

It asks the model to return only JSON:

```json
{"tool": "<tool_name_or_null>", "args": {}}
```

### 2) Optional tool execution

If the planner selects a known tool:

1. The Python handler executes.
2. The result is serialized.
3. Structured memory may be updated.
4. Tool result is added to the final prompt.

### 3) Final response pass

The final prompt includes the same context plus tool execution output.

The model then produces the user-facing reply.

This planner/tool/final-response pattern keeps the agent predictable and easier to debug.

## LLM Provider

The current provider is Gemini on Vertex AI:

```python
client = genai.Client(
    vertexai=True,
    project=self.project_id,
    location=self.location,
)
```

The provider exposes a simple method:

```python
async def generate(self, prompt: str) -> str
```

For portability, another project can swap this provider for:

- OpenAI
- Anthropic
- local model
- another Vertex AI model

The rest of the agent flow can remain the same if the provider returns plain text.

## Outbound WhatsApp Sending

Outbound WhatsApp is handled by `app/integrations/twilio_whatsapp.py`.

The sender formats the address:

```python
whatsapp:+256...
```

Then sends:

```python
client.messages.create(
    from_=from_addr,
    body=message,
    to=to_addr,
)
```

The pipeline calls this through a callback:

```python
outbound_send=lambda to, msg: twilio_whatsapp.send_whatsapp(to, msg)
```

This callback pattern is important because it keeps the pipeline channel-agnostic.

If `outbound_send` is absent, the same pipeline can fall back to SMS.

## Guardrails

The pipeline wraps the agent with guardrails:

### Input guardrail

Rejects:

- empty messages
- overly long messages
- messages without basic intent signal

### Output validation

Checks:

- reply is not too short
- prices mentioned by the model exist in DB
- suspicious product names are logged

### Output formatting

Applies channel-specific formatting:

- WhatsApp keeps markdown and truncates at a higher length
- SMS strips markdown and truncates aggressively

This is a good pattern for another project:

- validate before the LLM
- validate after the LLM
- format only after validation

## Minimal Porting Blueprint

To reuse this in another project, copy the architecture, not necessarily every file.

### 1) Create webhook route

```python
@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    await run_pipeline(
        db=db,
        from_raw=str(form.get("From", "")),
        text_raw=str(form.get("Body", "")).strip(),
        owner_phone=settings.owner_phone,
        outbound_send=lambda to, msg: send_whatsapp(to, msg),
    )
    return PlainTextResponse("OK", status_code=200)
```

### 2) Create reusable pipeline

Pipeline should own:

- normalization
- persistence
- guardrails
- role resolution
- agent call
- response validation
- dispatch

### 3) Create session class

Session should own:

- role
- user/customer/session id
- loading history
- loading structured memory
- selecting tools
- selecting guidelines
- calling engine

### 4) Create tool registry

Tools should wrap service functions.

Do not put business logic directly inside prompts.

### 5) Create provider interface

Use one method:

```python
async def generate(prompt: str) -> str:
    ...
```

Then keep the engine independent of the model vendor.

### 6) Store both messages and state

Minimum tables:

- `users` or `customers`
- `messages`
- `conversation_states`

Recommended message fields:

- `id`
- `user_id`
- `direction`
- `message`
- `created_at`

Recommended state fields:

- `user_id`
- `state_json`
- `updated_at`

## Recommended Sequence Diagram

```text
Twilio WhatsApp
    -> FastAPI /api/webhook/whatsapp
    -> run_pipeline()
    -> normalize_inbound()
    -> persist_inbound()
    -> InputGuardrail
    -> AfrisaleSession.run_turn()
        -> load guidelines
        -> load tools
        -> load recent messages
        -> load structured memory
        -> build_engine()
        -> planner LLM call
        -> optional tool call
        -> save memory update
        -> final LLM call
    -> OutputValidationGuardrail
    -> OutputFormattingGuardrail
    -> persist_outbound()
    -> twilio_whatsapp.send_whatsapp()
    -> Twilio sends user reply
```

## Key Design Principles to Preserve

- Keep webhook thin.
- Keep channel-specific logic at the edge.
- Persist inbound before calling the LLM.
- Keep business logic in services.
- Expose business operations to the LLM only through tools.
- Store short-term history separately from structured memory.
- Run output validation before sending.
- Make the model provider replaceable.

## Known Limitations in Current Implementation

- WhatsApp media fields are not parsed yet.
- Current outbound WhatsApp sender is text-only.
- `messages` table stores only text, not attachments.
- The engine uses a local fallback if Parlant's installed package cannot be instantiated.
- Tool execution is intentionally narrow and service-bound.

## Summary

Afrisale's conversational system is built around a clean separation:

- WhatsApp webhook receives and sends messages.
- Pipeline controls lifecycle and safety.
- Session assembles conversation context.
- Engine handles planning/tool use/final response.
- Tools expose business actions.
- Provider handles model inference.
- Database stores message history and structured memory.

This structure is reusable in another project because most project-specific logic lives in guidelines, tools, and service functions, while the conversational shell remains generic.
