"""
Smoke test for GCS access using ADC from .env.

Loads GOOGLE_APPLICATION_CREDENTIALS and GCS_BUCKET_PRODUCTS from .env so
the script works without exporting env vars manually.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent
load_dotenv(REPO_ROOT / ".env")

cred_path = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
if cred_path and not Path(cred_path).exists():
    raise SystemExit(f"GOOGLE_APPLICATION_CREDENTIALS path not found: {cred_path}")
if cred_path:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path

bucket_name = (os.getenv("GCS_BUCKET_PRODUCTS") or "afrisale-mvp-bucket").strip()
project_id = (os.getenv("GCP_PROJECT_ID") or "").strip() or None

from google.cloud import storage  # noqa: E402

client = storage.Client(project=project_id)
bucket = client.bucket(bucket_name)

blob = bucket.blob("test.txt")
blob.upload_from_string("hello world")

print(f"Uploaded gs://{bucket_name}/test.txt")
