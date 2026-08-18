from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

import httpx

from app.models import TicketResult
from mockdesk.store import MockDeskStore

_RETRYABLE_STATUS_CODES = {429, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 0.5
_BACKOFF_CAP_SECONDS = 8.0


class MockDeskUnavailableError(RuntimeError):
    """Raised when MockDesk stays unavailable after bounded retries."""


class MockDeskGateway(Protocol):
    def create_ticket(self, payload: dict[str, object], idempotency_key: str) -> TicketResult: ...


class InProcessMockDeskGateway:
    def __init__(self, store: MockDeskStore) -> None:
        self._store = store

    def create_ticket(self, payload: dict[str, object], idempotency_key: str) -> TicketResult:
        return self._store.create_ticket(payload, idempotency_key)


class HttpMockDeskGateway:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._sleep = sleep
        self._transport = transport

    def create_ticket(self, payload: dict[str, object], idempotency_key: str) -> TicketResult:
        last_failure = "no attempt made"
        with httpx.Client(transport=self._transport, timeout=self._timeout_seconds) as client:
            for attempt in range(_MAX_ATTEMPTS):
                retry_after = None
                try:
                    response = client.post(
                        f"{self._base_url}/tickets",
                        json=payload,
                        headers={"Idempotency-Key": idempotency_key},
                    )
                except httpx.TransportError as exc:
                    last_failure = f"transport error: {exc}"
                else:
                    if response.status_code not in _RETRYABLE_STATUS_CODES:
                        response.raise_for_status()
                        return TicketResult.model_validate(response.json())
                    last_failure = f"HTTP {response.status_code}"
                    retry_after = response.headers.get("Retry-After")
                if attempt < _MAX_ATTEMPTS - 1:
                    self._sleep(_retry_delay(attempt, retry_after))
        raise MockDeskUnavailableError(
            f"MockDesk unavailable after {_MAX_ATTEMPTS} attempts (last failure: {last_failure})"
        )


def _retry_delay(attempt: int, retry_after: str | None) -> float:
    if retry_after is not None:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return min(_BACKOFF_BASE_SECONDS * (2**attempt), _BACKOFF_CAP_SECONDS)
