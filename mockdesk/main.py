from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.models import TicketResult
from mockdesk.store import MockDeskStore


class TicketPayload(BaseModel):
    request_id: str
    summary: str
    decision_status: str | None = None
    reasons: list[str] = []


app = FastAPI(title="MockDesk", version="0.1.0")
store = MockDeskStore(Path(os.getenv("MOCKDESK_DB_PATH", "runtime/mockdesk.db")))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tickets", response_model=TicketResult)
def create_ticket(
    payload: TicketPayload,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TicketResult:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    return store.create_ticket(payload.model_dump(), idempotency_key=idempotency_key)
