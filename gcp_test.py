import os
from pathlib import Path

import google.auth
from dotenv import load_dotenv
from google.auth.exceptions import DefaultCredentialsError
from vertexai.generative_models import GenerativeModel
import vertexai


def main() -> int:
    load_dotenv()

    project_id = os.getenv("GCP_PROJECT_ID", "ai-fest26")
    location = os.getenv("GCP_LOCATION", "us-central1")
    model_name = os.getenv("GCP_MODEL", "gemini-2.5-flash")
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if credentials_path and not Path(credentials_path).exists():
        print(f"GOOGLE_APPLICATION_CREDENTIALS path not found: {credentials_path}")
        return 1

    try:
        google.auth.default()
    except DefaultCredentialsError:
        print("Missing GCP Application Default Credentials (ADC).")
        print("Set a service account key path in GOOGLE_APPLICATION_CREDENTIALS,")
        print("or run: gcloud auth application-default login")
        return 0

    vertexai.init(project=project_id, location=location)
    model = GenerativeModel(model_name)
    response = model.generate_content("Explain agent systems simply")
    print(response.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())