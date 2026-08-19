from __future__ import annotations

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
AUDIT = {"X-Demo-Role": "solution_engineer", "X-Demo-User": "solution_engineer"}


def build_client(tmp_path: Path) -> tuple[TestClient, MockDeskStore]:
    mockdesk = MockDeskStore(tmp_path / "mockdesk.db")
    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(mockdesk),
        project_root=ROOT,
    )
    return TestClient(create_app(service=service)), mockdesk


def hero_payload(received_quotes: int) -> dict:
    return {
        "request_id": "PR-2026-0042",
        "request_date": "2026-08-18",
        "supplier_name": "Atlas Endüstri",
        "category": "SPARE_PARTS",
        "amount_try": "220000",
        "received_quotes": received_quotes,
        "offered_lead_time_days": 20,
    }


def quote_exception_payload(received_quotes: int) -> dict:
    return {
        "request_id": "PR-2026-QUOTE",
        "request_date": "2026-08-18",
        "supplier_name": "Ege Parça",
        "category": "SPARE_PARTS",
        "amount_try": "150000",
        "received_quotes": received_quotes,
        "offered_lead_time_days": 10,
    }


def analyze(client: TestClient, payload: dict) -> dict:
    response = client.post("/api/v1/requests/analyze", headers=PROCUREMENT, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def audit_events(client: TestClient) -> list[dict]:
    response = client.get("/api/v1/audit/events", headers=AUDIT)
    assert response.status_code == 200
    return response.json()


def test_identical_reanalysis_reuses_the_pending_approval(tmp_path: Path) -> None:
    client, mockdesk = build_client(tmp_path)

    first = analyze(client, hero_payload(received_quotes=1))["approval"]
    second = analyze(client, hero_payload(received_quotes=1))["approval"]

    assert second["approval_id"] == first["approval_id"]
    approval_id = first["approval_id"]
    event_types = [event["event_type"] for event in audit_events(client)]
    assert event_types.count("APPROVAL_REQUESTED") == 1
    assert event_types.count("APPROVAL_REUSED") == 1

    approved = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)
    assert approved.status_code == 200
    executed = client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=PROCUREMENT)
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "OPEN"

    analyze(client, hero_payload(received_quotes=1))
    replayed = client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=PROCUREMENT)

    assert replayed.status_code == 200
    assert replayed.json()["ticket_id"] == executed.json()["ticket_id"]
    assert mockdesk.ticket_count() == 1


def test_corrected_reanalysis_supersedes_the_stale_pending_approval(tmp_path: Path) -> None:
    client, _mockdesk = build_client(tmp_path)

    stale_id = analyze(client, hero_payload(received_quotes=1))["approval"]["approval_id"]
    revised_id = analyze(client, hero_payload(received_quotes=2))["approval"]["approval_id"]

    assert revised_id != stale_id
    superseded = [
        event for event in audit_events(client) if event["event_type"] == "APPROVAL_SUPERSEDED"
    ]
    assert [event["approval_id"] for event in superseded] == [stale_id]
    assert superseded[0]["details"]["superseded_by"] == revised_id

    stale_approval = client.post(f"/api/v1/approvals/{stale_id}/approve", headers=FINANCE)
    assert stale_approval.status_code == 409
    assert stale_approval.json()["error"]["code"] == "INVALID_APPROVAL_STATE"

    approved = client.post(f"/api/v1/approvals/{revised_id}/approve", headers=FINANCE)
    assert approved.status_code == 200
    executed = client.post(f"/api/v1/tool-actions/{revised_id}/execute", headers=PROCUREMENT)
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "OPEN"


def test_correction_that_clears_the_exception_supersedes_the_stale_approval(
    tmp_path: Path,
) -> None:
    client, mockdesk = build_client(tmp_path)

    stale = analyze(client, quote_exception_payload(received_quotes=1))["approval"]
    stale_id = stale["approval_id"]
    cleared = analyze(client, quote_exception_payload(received_quotes=2))

    assert cleared["decision"]["decision_status"] == "APPROVED"
    assert cleared["approval"] is None
    superseded = [
        event for event in audit_events(client) if event["event_type"] == "APPROVAL_SUPERSEDED"
    ]
    assert [event["approval_id"] for event in superseded] == [stale_id]
    assert superseded[0]["details"]["superseded_by"] is None

    approved = client.post(f"/api/v1/approvals/{stale_id}/approve", headers=FINANCE)
    executed = client.post(f"/api/v1/tool-actions/{stale_id}/execute", headers=PROCUREMENT)

    assert approved.status_code == 409
    assert executed.status_code == 409
    assert mockdesk.ticket_count() == 0


def test_revision_after_a_granted_approval_supersedes_it(tmp_path: Path) -> None:
    client, mockdesk = build_client(tmp_path)
    granted_id = analyze(client, hero_payload(received_quotes=1))["approval"]["approval_id"]
    granted = client.post(f"/api/v1/approvals/{granted_id}/approve", headers=FINANCE)
    assert granted.status_code == 200

    revised_id = analyze(client, hero_payload(received_quotes=2))["approval"]["approval_id"]

    assert revised_id != granted_id
    superseded = [
        event for event in audit_events(client) if event["event_type"] == "APPROVAL_SUPERSEDED"
    ]
    assert [event["approval_id"] for event in superseded] == [granted_id]

    blocked = client.post(f"/api/v1/tool-actions/{granted_id}/execute", headers=PROCUREMENT)

    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "APPROVAL_REQUIRED"
    assert mockdesk.ticket_count() == 0


def test_identical_reanalysis_after_execution_reuses_the_granted_approval(tmp_path: Path) -> None:
    client, mockdesk = build_client(tmp_path)
    approval_id = analyze(client, hero_payload(received_quotes=1))["approval"]["approval_id"]
    client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)
    executed = client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=PROCUREMENT)
    assert executed.status_code == 200, executed.text

    replayed = analyze(client, hero_payload(received_quotes=1))["approval"]

    assert replayed["approval_id"] == approval_id
    assert replayed["status"] == "APPROVED"
    event_types = [event["event_type"] for event in audit_events(client)]
    assert event_types.count("APPROVAL_REQUESTED") == 1
    assert mockdesk.ticket_count() == 1


def test_superseded_approval_cannot_execute(tmp_path: Path) -> None:
    client, mockdesk = build_client(tmp_path)
    stale_id = analyze(client, hero_payload(received_quotes=1))["approval"]["approval_id"]
    analyze(client, hero_payload(received_quotes=2))

    approved = client.post(f"/api/v1/approvals/{stale_id}/approve", headers=FINANCE)
    response = client.post(f"/api/v1/tool-actions/{stale_id}/execute", headers=PROCUREMENT)

    assert approved.status_code == 409
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPROVAL_REQUIRED"
    assert mockdesk.ticket_count() == 0
