# Image Search MVP — Smoke Test Plan

This is the manual test pass to run after image search MVP is deployed.
Each test lists prerequisites, the action, and what to verify.

## Prerequisites (one-time)

1. GCP project has Vertex AI enabled.
2. GCS bucket exists and the service account has `Storage Object Admin`.
3. Vertex AI Vector Search index has been created and deployed to an
   `IndexEndpoint`. Set in `.env`:
   - `VERTEX_VECTOR_INDEX_ID`
   - `VERTEX_VECTOR_INDEX_ENDPOINT_ID`
   - `VERTEX_VECTOR_DEPLOYED_INDEX_ID`
   - `VERTEX_VECTOR_DIMENSIONS=1408`
4. `.env` has `GCS_BUCKET_PRODUCTS=<bucket>`.
5. `GOOGLE_APPLICATION_CREDENTIALS` points at a working service account
   JSON, OR `gcloud auth application-default login` has been run.
6. Twilio sandbox or production WhatsApp sender configured.
7. Catalog seeded with at least 3 products.
8. `python scripts/seed_product_images.py --dir ./catalog_assets` has been
   run to populate `product_images` and the Vector Search index.

## Test 1 — Image-only inbound (the headline flow)

**Action:** From WhatsApp, send a single product image (no caption) to the
bot, where the image visually resembles a product in the seeded catalog
(e.g., a black leather belt photo while a similar belt exists).

**Expected:**

- Webhook receives `NumMedia=1`, `MediaUrl0`, `MediaContentType0=image/jpeg`.
- Server logs:
  - `whatsapp_webhook keys=... num_media=1`
  - `gcs_upload ok object=inbound/...`
  - `vvs_upsert` is NOT called (this is a query, not ingest).
  - planner stage attempts `find_products_by_image`.
- User receives **one media message** (image + caption) showing the top
  match's photo, name, price, and variants.
- User receives **one follow-up text message** listing 1-3 alternates with
  name + price.
- `messages` table shows one inbound row with `message_type='media'` and
  one outbound row.
- `message_attachments` has the inbound image with `gcs_uri` populated.

## Test 2 — Image with caption ("do you have something like this?")

**Action:** Same as Test 1 but include a text body alongside the image.

**Expected:** Same result as Test 1. The text caption does not change the
behavior because the planner forces the image-search tool whenever an
image is attached.

## Test 3 — Text-first descriptive query ("show me Air Jordans")

**Action:** Send a text-only WhatsApp message, e.g., `show me Air Jordans`.

**Expected:**

- Pipeline calls `search_products` (or falls back to `find_products_by_text`
  via multimodal text embedding) and returns matches.
- User receives **one media message** (top match image + caption) when the
  top match has an image, OR a text-only reply if no images are attached
  to that product.
- Alternates message lists similar products by name and price.

## Test 4 — Text-first when nothing matches

**Action:** Send a text-only message asking for a product that does not
exist (e.g., `do you sell snowboards?`).

**Expected:**

- `search_products` and `find_products_by_text` return empty.
- User receives a text-only reply that says we don't carry that product
  and offers to help search for something else.
- No outbound media message is sent.

## Test 5 — Image with no visual match

**Action:** Send an image that does not resemble anything in the catalog
(e.g., a photo of a car when the catalog is clothing-only).

**Expected:**

- `find_products_by_image` returns empty after similarity threshold filter.
- User receives a text-only reply explaining no match and offering text
  search.
- No outbound media message is sent.

## Test 6 — Oversized / disallowed media

**Action:** Send an inbound media file whose MIME is not in
`IMAGE_ALLOWED_MIMES` (e.g., a video) or whose size exceeds
`IMAGE_MAX_BYTES`.

**Expected:**

- Server logs `inbound_media_mime_blocked` or `inbound_media_too_large`.
- The inbound message is still saved (text-only) but no attachment row is
  created.
- Pipeline runs as a normal text turn.
- User receives a text reply (no image-search performed).

## Test 7 — SMS fallback (no media)

**Action:** Hit `POST /api/webhook` (JSON channel) with a text product
query. Africa's Talking is the dispatch path.

**Expected:**

- The same pipeline runs but `outbound_send` is None, so the dispatch
  stage uses SMS.
- If the agent's reply has a `media_url`, dispatch falls back to
  text-only (alternates appended with two newlines) so the message still
  reads sensibly on SMS.

## Test 8 — Owner-side `add_product_image` (smoke only, no UI yet)

**Action:** In `scripts/agent_test.py` style script, send an inbound image
from the owner phone with text like `add this image to product 1`.

**Expected:**

- Planner picks `add_product_image` (owner role).
- A new `product_images` row is created with `vector_datapoint_id`
  populated.
- A new datapoint exists in Vertex AI Vector Search.
- Subsequent customer image queries can match against the new image.

## Quick offline sanity (no Twilio, no GCP)

```bash
python -c "import asyncio; import app.models.models; \
from app.core.database import Base, SessionLocal, engine; \
from app.core.migrations import ensure_schema; \
Base.metadata.create_all(bind=engine); ensure_schema(engine); \
from app.pipeline.runner import run_pipeline; \
db=SessionLocal(); \
print(asyncio.run(run_pipeline(db=db, from_raw='+19995550999', \
text_raw='Please list available products.', owner_phone='', outbound_send=None))[:200]); \
db.close()"
```

Expect a non-empty product reply. If you see
`table messages has no column named channel`, run the same command twice;
`ensure_schema` will add the column on first run.

## What to check in the DB after a media turn

```sql
SELECT id, customer_id, direction, channel, message_type, length(message)
FROM messages ORDER BY id DESC LIMIT 5;

SELECT id, message_id, kind, mime_type, bytes_size, gcs_uri
FROM message_attachments ORDER BY id DESC LIMIT 5;

SELECT pi.id, p.name, pi.is_primary, pi.vector_datapoint_id, pi.gcs_uri
FROM product_images pi JOIN products p ON p.id = pi.product_id
ORDER BY pi.id DESC LIMIT 5;
```
