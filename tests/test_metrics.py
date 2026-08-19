from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.metrics import summarize
from app.mockdesk_client import InProcessMockDeskGateway
from app.models import AuditEvent
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore

ROOT = Path(__file__).resolve().parents[1]
PROCUREMENT_HEADERS = {
    "X-Demo-Role": "procurement_specialist",
    "X-Demo-User": "procurement_user",
}
FINANCE_HEADERS = {"X-Demo-Role": "finance_approver", "X-Demo-User": "finance_user"}
METRICS_HEADERS = {"X-Demo-Role": "solution_engineer", "X-Demo-User": "solution_engineer"}

HERO_PAYLOAD = {
    "request_id": "PR-2026-0042",
    "request_date": "2026-08-18",
    "supplier_name": "Atlas Endüstri",
    "category": "SPARE_PARTS",
    "amount_try": "220000",
    "received_quotes": 1,
    "offered_lead_time_days": 20,
}


def build_client(tmp_path: Path) -> TestClient:
    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        project_root=ROOT,
    )
    return TestClient(create_app(service=service))


def _event(
    event_type: str,
    *,
    request_id: str | None = None,
    details: dict | None = None,
    at: datetime | None = None,
) -> AuditEvent:
    return AuditEvent(
        event_id=f"EV-{event_type}-{request_id or 'NONE'}",
        timestamp=at or datetime(2026, 8, 18, 9, 0, tzinfo=UTC),
        event_type=event_type,
        actor="test",
        request_id=request_id,
        approval_id=None,
        trace_id="trace-test",
        details=details or {},
    )


def test_summarize_counts_decisions_duplicates_and_cycle_time() -> None:
    start = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)
    events = [
        _event("REQUEST_RECEIVED", request_id="PR-1", at=start),
        _event(
            "POLICY_EVALUATED",
            request_id="PR-1",
            details={"decision_status": "CONDITIONAL_REVIEW"},
        ),
        _event("APPROVAL_GRANTED", request_id="PR-1"),
        _event(
            "TOOL_EXECUTED",
            request_id="PR-1",
            details={"status": "OPEN"},
            at=start + timedelta(seconds=90),
        ),
        _event("TOOL_EXECUTED", request_id="PR-1", details={"status": "ALREADY_PROCESSED"}),
        _event("REQUEST_RECEIVED", request_id="PR-2", at=start),
        _event("POLICY_EVALUATED", request_id="PR-2", details={"decision_status": "REJECTED"}),
        _event("SECURITY_CONTENT_QUARANTINED", request_id="PR-2"),
        _event("TOOL_EXECUTION_DENIED", request_id="PR-2"),
    ]

    summary = summarize(events)

    assert summary["analyses_total"] == 2
    assert summary["decisions"] == {"APPROVED": 0, "CONDITIONAL_REVIEW": 1, "REJECTED": 1}
    assert summary["approvals"]["granted"] == 1
    assert summary["tickets_created"] == 1
    assert summary["duplicates_prevented"] == 1
    assert summary["quarantined_attachments"] == 1
    assert summary["denied_or_blocked_actions"] == 1
    assert summary["completed_requests"] == 1
    assert summary["median_cycle_time_seconds"] == 90.0


def test_summarize_handles_no_completed_requests() -> None:
    summary = summarize([_event("REQUEST_RECEIVED", request_id="PR-1")])

    assert summary["completed_requests"] == 0
    assert summary["median_cycle_time_seconds"] is None


def test_metrics_endpoint_reports_the_hero_flow(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    analyzed = client.post(
        "/api/v1/requests/analyze", headers=PROCUREMENT_HEADERS, json=HERO_PAYLOAD
    )
    approval_id = analyzed.json()["approval"]["approval_id"]
    client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE_HEADERS)
    client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=PROCUREMENT_HEADERS)
    client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=PROCUREMENT_HEADERS)

    response = client.get("/api/v1/metrics/summary", headers=METRICS_HEADERS)

    assert response.status_code == 200
    summary = response.json()
    assert summary["decisions"]["CONDITIONAL_REVIEW"] == 1
    assert summary["tickets_created"] == 1
    assert summary["duplicates_prevented"] == 1
    assert summary["quarantined_attachments"] == 1
    assert summary["completed_requests"] == 1
    assert summary["median_cycle_time_seconds"] is not None


def test_metrics_endpoint_requires_an_authorized_role(tmp_path: Path) -> None:
    response = build_client(tmp_path).get(
        "/api/v1/metrics/summary", headers=PROCUREMENT_HEADERS
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_home_ships_the_metrics_panel(tmp_path: Path) -> None:
    html = build_client(tmp_path).get("/").text

    assert 'id="metrics-summary"' in html
    assert 'id="metrics-button"' in html
