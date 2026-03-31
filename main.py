import app.models.models  # noqa: F401 — register ORM metadata

from fastapi import FastAPI

from app.api.messages import router
from app.core.database import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Afrisale MVP")
app.include_router(router)
