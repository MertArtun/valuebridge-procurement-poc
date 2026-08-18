from __future__ import annotations

from typing import Protocol

import httpx

from app.models import TicketResult
from mockdesk.store import MockDeskStore


class MockDeskGateway(Protocol):
    def create_ticket(self, payload: dict[str, object], idempotency_key: str) -> TicketResult: ...


class InProcessMockDeskGateway:
    def __init__(self, store: MockDeskStore) -> None:
        self._store = store

    def create_ticket(self, payload: dict[str, object], idempotency_key: str) -> TicketResult:
        return self._store.create_ticket(payload, idempotency_key)


class HttpMockDeskGateway:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def create_ticket(self, payload: dict[str, object], idempotency_key: str) -> TicketResult:
        response = httpx.post(
            f"{self._base_url}/tickets",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        return TicketResult.model_validate(response.json())
