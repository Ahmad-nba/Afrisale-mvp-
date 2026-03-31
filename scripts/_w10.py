import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def w(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip("\n") + "\n", encoding="utf-8")

w("app/schemas/schemas.py", r"""
from pydantic import BaseModel, ConfigDict, Field


class WebhookPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(..., alias="from")
    text: str
""")
print("schemas fix")
