from pydantic import BaseModel, ConfigDict, Field


class WebhookPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(..., alias="from")
    text: str
