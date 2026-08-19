from __future__ import annotations

import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.errors import (
    IdempotencyConflictError,
    MockDeskRequestError,
    MockDeskUnavailableError,
)
from app.models import TicketResult
from mockdesk.store import MockDeskStore

_RETRYABLE_STATUS_CODES = {429, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 0.5
_BACKOFF_CAP_SECONDS = 8.0


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
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._sleep = sleep
        self._transport = transport
        self._now = now

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
                    if response.status_code == 409:
                        message = _response_error_message(response)
                        raise IdempotencyConflictError(message)
                    if response.status_code not in _RETRYABLE_STATUS_CODES:
                        if response.is_error:
                            raise MockDeskRequestError(
                                f"MockDesk returned HTTP {response.status_code}: "
                                f"{_response_error_message(response)}"
                            )
                        result = _parse_ticket_result(response)
                        if result.request_id != str(payload.get("request_id")):
                            raise MockDeskRequestError(
                                "MockDesk success response did not match the "
                                f"submitted request (HTTP {response.status_code})"
                            )
                        return result
                    last_failure = f"HTTP {response.status_code}"
                    retry_after = response.headers.get("Retry-After")
                if attempt < _MAX_ATTEMPTS - 1:
                    self._sleep(_retry_delay(attempt, retry_after, now=self._now()))
        raise MockDeskUnavailableError(
            f"MockDesk unavailable after {_MAX_ATTEMPTS} attempts (last failure: {last_failure})"
        )


def _parse_ticket_result(response: httpx.Response) -> TicketResult:
    try:
        return TicketResult.model_validate(response.json())
    except (ValidationError, ValueError) as exc:
        raise MockDeskRequestError(
            f"MockDesk returned an invalid success response (HTTP {response.status_code})"
        ) from exc


def _response_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        # A non-JSON error body may carry downstream internals (stack traces,
        # configuration); never echo it to the caller or the audit trail.
        return response.reason_phrase or "unreadable error body"
    if isinstance(body, dict):
        if isinstance(body.get("error"), dict):
            return str(body["error"].get("message") or body["error"])
        detail = body.get("detail")
        if isinstance(detail, list):
            parts = []
            for item in detail:
                if isinstance(item, dict):
                    loc = ".".join(str(piece) for piece in item.get("loc", []))
                    parts.append(f"{loc}: {item.get('msg', 'invalid')}")
                else:
                    parts.append(str(item))
            return "; ".join(parts) or "validation error"
        if detail is not None:
            return str(detail)
    return str(body)


def _retry_delay(attempt: int, retry_after: str | None, *, now: datetime | None = None) -> float:
    fallback = min(_BACKOFF_BASE_SECONDS * (2**attempt), _BACKOFF_CAP_SECONDS)
    if retry_after is None:
        return fallback

    try:
        parsed_seconds = float(retry_after)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(retry_after)
        except (TypeError, ValueError, OverflowError):
            return fallback
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        reference = now or datetime.now(UTC)
        parsed_seconds = (retry_at - reference).total_seconds()

    if not math.isfinite(parsed_seconds):
        return fallback
    return min(max(parsed_seconds, 0.0), _BACKOFF_CAP_SECONDS)


__all__ = [
    "HttpMockDeskGateway",
    "InProcessMockDeskGateway",
    "MockDeskGateway",
    "MockDeskRequestError",
    "MockDeskUnavailableError",
    "_retry_delay",
]
