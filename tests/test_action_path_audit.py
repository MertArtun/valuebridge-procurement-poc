from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore

ROOT = Path(__file__).resolve().parents[1]
PROCUREMENT = {"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"}
FINANCE = {"X-Demo-Role": "finance_approver", "X-Demo-User": "finance_user"}
AUDIT = {"X-Demo-Role": "auditor", "X-Demo-User": "auditor_user"}

HERO_REQUEST = {
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


def audit_events(client: TestClient) -> list[dict]:
    response = client.get("/api/v1/audit/events", headers=AUDIT)
    assert response.status_code == 200
    return response.json()


def pending_approval(client: TestClient) -> str:
    analyzed = client.post("/api/v1/requests/analyze", headers=PROCUREMENT, json=HERO_REQUEST)
    assert analyzed.status_code == 200
    return analyzed.json()["approval"]["approval_id"]


def grant_approval(client: TestClient, approval_id: str) -> None:
    approved = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)
    assert approved.status_code == 200


def test_execution_before_approval_is_blocked_and_traced(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    approval_id = pending_approval(client)

    response = client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=PROCUREMENT)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "APPROVAL_REQUIRED"
    assert error["trace_id"] is not None and error["trace_id"].startswith("trace-")
    blocked = [e for e in audit_events(client) if e["event_type"] == "TOOL_EXECUTION_BLOCKED"]
    assert len(blocked) == 1
    assert blocked[0]["approval_id"] == approval_id
    assert blocked[0]["trace_id"] == error["trace_id"]
    assert blocked[0]["details"]["status"] == "PENDING"


def test_execution_by_an_unauthorized_role_is_denied_and_attributed(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    approval_id = pending_approval(client)
    grant_approval(client, approval_id)

    response = client.post(
        f"/api/v1/tool-actions/{approval_id}/execute",
        headers={"X-Demo-Role": "auditor", "X-Demo-User": "mallory"},
    )

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["trace_id"] is not None and error["trace_id"].startswith("trace-")
    denied = [e for e in audit_events(client) if e["event_type"] == "TOOL_EXECUTION_DENIED"]
    assert len(denied) == 1
    assert denied[0]["actor"] == "mallory"
    assert denied[0]["details"]["role"] == "auditor"


def test_approval_by_a_non_approver_role_is_denied_and_audited(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    approval_id = pending_approval(client)

    response = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "mallory"},
    )

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["trace_id"] is not None and error["trace_id"].startswith("trace-")
    denied = [e for e in audit_events(client) if e["event_type"] == "APPROVAL_DENIED"]
    assert len(denied) == 1
    assert denied[0]["actor"] == "mallory"
    assert denied[0]["approval_id"] == approval_id


def test_denied_action_paths_record_a_bounded_approval_id(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    oversized_id = "AP-" + "X" * 5000
    intruder = {"X-Demo-Role": "auditor", "X-Demo-User": "mallory"}

    denied = client.post(f"/api/v1/approvals/{oversized_id}/approve", headers=intruder)
    blocked = client.post(f"/api/v1/tool-actions/{oversized_id}/execute", headers=intruder)

    assert denied.status_code == 403
    assert blocked.status_code == 403
    recorded = [
        event["approval_id"]
        for event in audit_events(client)
        if event["event_type"] in {"APPROVAL_DENIED", "TOOL_EXECUTION_DENIED"}
    ]
    assert len(recorded) == 2
    assert all(len(value) <= 64 for value in recorded)


def test_rejection_after_approval_records_the_failed_transition(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    approval_id = pending_approval(client)
    grant_approval(client, approval_id)

    response = client.post(f"/api/v1/approvals/{approval_id}/reject", headers=FINANCE)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INVALID_APPROVAL_STATE"
    assert error["trace_id"] is not None and error["trace_id"].startswith("trace-")
    failed = [e for e in audit_events(client) if e["event_type"] == "APPROVAL_TRANSITION_FAILED"]
    assert len(failed) == 1
    assert failed[0]["approval_id"] == approval_id
    assert failed[0]["request_id"] == HERO_REQUEST["request_id"]
    assert failed[0]["details"]["target_status"] == "REJECTED"
    assert failed[0]["details"]["current_status"] == "APPROVED"
