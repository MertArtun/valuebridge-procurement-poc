from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.mockdesk_client import HttpMockDeskGateway, MockDeskUnavailableError
from app.service import ProcurementService
from app.store import SQLiteStore

TICKET_JSON = {
    "ticket_id": "MD-1001",
    "status": "OPEN",
    "request_id": "PR-2026-0042",
    "duplicate_created": False,
}

PAYLOAD = {"request_id": "PR-2026-0042", "summary": "Procurement Exception Review"}
IDEMPOTENCY_KEY = "PR-2026-0042-PROCUREMENT-REVIEW"


def build_gateway(handler, sleeps: list[float]) -> tuple[HttpMockDeskGateway, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(len(requests), request)

    gateway = HttpMockDeskGateway(
        "http://mockdesk",
        transport=httpx.MockTransport(recording_handler),
        sleep=sleeps.append,
    )
    return gateway, requests


def test_transient_503_is_retried_with_same_idempotency_key() -> None:
    sleeps: list[float] = []

    def handler(call_number: int, _request: httpx.Request) -> httpx.Response:
        if call_number == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=TICKET_JSON)

    gateway, requests = build_gateway(handler, sleeps)

    result = gateway.create_ticket(PAYLOAD, idempotency_key=IDEMPOTENCY_KEY)

    assert result.ticket_id == "MD-1001"
    assert len(requests) == 2
    assert [request.headers["Idempotency-Key"] for request in requests] == [
        IDEMPOTENCY_KEY,
        IDEMPOTENCY_KEY,
    ]
    assert len(sleeps) == 1


def test_client_error_400_is_not_retried() -> None:
    sleeps: list[float] = []

    def handler(_call_number: int, _request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "bad payload"})

    gateway, requests = build_gateway(handler, sleeps)

    with pytest.raises(httpx.HTTPStatusError):
        gateway.create_ticket(PAYLOAD, idempotency_key=IDEMPOTENCY_KEY)

    assert len(requests) == 1
    assert sleeps == []


def test_client_cancellation_499_is_not_retried() -> None:
    sleeps: list[float] = []

    def handler(_call_number: int, _request: httpx.Request) -> httpx.Response:
        return httpx.Response(499)

    gateway, requests = build_gateway(handler, sleeps)

    with pytest.raises(httpx.HTTPStatusError):
        gateway.create_ticket(PAYLOAD, idempotency_key=IDEMPOTENCY_KEY)

    assert len(requests) == 1
    assert sleeps == []


def test_retry_after_header_is_respected() -> None:
    sleeps: list[float] = []

    def handler(call_number: int, _request: httpx.Request) -> httpx.Response:
        if call_number == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json=TICKET_JSON)

    gateway, _requests = build_gateway(handler, sleeps)

    gateway.create_ticket(PAYLOAD, idempotency_key=IDEMPOTENCY_KEY)

    assert sleeps == [7.0]


def test_persistent_503_fails_after_bounded_attempts() -> None:
    sleeps: list[float] = []

    def handler(_call_number: int, _request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    gateway, requests = build_gateway(handler, sleeps)

    with pytest.raises(MockDeskUnavailableError):
        gateway.create_ticket(PAYLOAD, idempotency_key=IDEMPOTENCY_KEY)

    assert len(requests) == 3
    assert len(sleeps) == 2


def test_transport_interruption_is_retried() -> None:
    sleeps: list[float] = []

    def handler(call_number: int, request: httpx.Request) -> httpx.Response:
        if call_number == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json=TICKET_JSON)

    gateway, requests = build_gateway(handler, sleeps)

    result = gateway.create_ticket(PAYLOAD, idempotency_key=IDEMPOTENCY_KEY)

    assert result.status == "OPEN"
    assert len(requests) == 2


def test_final_mockdesk_failure_returns_502_and_is_audited(tmp_path: Path) -> None:
    class AlwaysDownGateway:
        def create_ticket(self, payload: dict[str, object], idempotency_key: str):
            raise MockDeskUnavailableError(
                "MockDesk unavailable after 3 attempts (last failure: HTTP 503)"
            )

    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=AlwaysDownGateway(),
        project_root=Path.cwd(),
    )
    client = TestClient(create_app(service=service))
    procurement = {"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"}
    finance = {"X-Demo-Role": "finance_approver", "X-Demo-User": "finance_user"}
    analyzed = client.post(
        "/api/v1/requests/analyze",
        headers=procurement,
        json={
            "request_id": "PR-2026-0042",
            "request_date": "2026-08-18",
            "supplier_name": "Atlas Endüstri",
            "category": "SPARE_PARTS",
            "amount_try": "220000",
            "received_quotes": 1,
            "offered_lead_time_days": 20,
        },
    )
    approval_id = analyzed.json()["approval"]["approval_id"]
    approved = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=finance)
    assert approved.status_code == 200

    response = client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=procurement)

    assert response.status_code == 502
    events = client.get("/api/v1/audit/events", headers=finance).json()
    failure_events = [event for event in events if event["event_type"] == "TOOL_EXECUTION_FAILED"]
    assert len(failure_events) == 1
    assert "MockDesk unavailable" in failure_events[0]["details"]["error"]


def test_backoff_grows_between_transient_failures() -> None:
    sleeps: list[float] = []

    def handler(call_number: int, _request: httpx.Request) -> httpx.Response:
        if call_number <= 2:
            return httpx.Response(503)
        return httpx.Response(200, json=TICKET_JSON)

    gateway, _requests = build_gateway(handler, sleeps)

    gateway.create_ticket(PAYLOAD, idempotency_key=IDEMPOTENCY_KEY)

    assert len(sleeps) == 2
    assert sleeps[1] > sleeps[0]
