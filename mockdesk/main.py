from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.errors import ValueBridgeError
from app.models import TicketResult
from mockdesk.store import MockDeskStore


class TicketPayload(BaseModel):
    request_id: str = Field(min_length=3, max_length=64)
    summary: str = Field(min_length=1, max_length=240)
    decision_status: str | None = None
    reasons: list[str] = Field(default_factory=list)


app = FastAPI(title="MockDesk", version="0.1.0")
store = MockDeskStore(Path(os.getenv("MOCKDESK_DB_PATH", "runtime/mockdesk.db")))


@app.exception_handler(ValueBridgeError)
async def valuebridge_error(_request, exc: ValueBridgeError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": str(exc),
                "trace_id": exc.trace_id,
                "retryable": exc.retryable,
            }
        },
    )


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
