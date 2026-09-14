from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="BuddyBird AI API", version="0.1.0")


class HealthResponse(BaseModel):
    status: Literal["ok"]


@app.get("/health", tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")
