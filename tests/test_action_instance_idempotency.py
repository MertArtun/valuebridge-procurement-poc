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


def build_client(tmp_path: Path, mockdesk_db: Path | None = None) -> TestClient:
    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(
            MockDeskStore(mockdesk_db or (tmp_path / "mockdesk.db"))
        ),
        project_root=ROOT,
    )
    return TestClient(create_app(service=service))


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


def analyze_approve_execute(client: TestClient, payload: dict) -> dict:
    analyzed = client.post("/api/v1/requests/analyze", headers=PROCUREMENT, json=payload)
    assert analyzed.status_code == 200
    approval_id = analyzed.json()["approval"]["approval_id"]
    approved = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)
    assert approved.status_code == 200
    executed = client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=PROCUREMENT)
    assert executed.status_code == 200, executed.text
    return executed.json()


def test_corrected_reanalysis_of_same_request_can_execute_again(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    first = analyze_approve_execute(client, hero_payload(received_quotes=1))
    second = analyze_approve_execute(client, hero_payload(received_quotes=2))

    assert first["status"] == "OPEN"
    assert second["status"] == "OPEN"
    assert second["ticket_id"] != first["ticket_id"]


def test_same_approval_replay_returns_the_original_ticket(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    analyzed = client.post(
        "/api/v1/requests/analyze", headers=PROCUREMENT, json=hero_payload(received_quotes=1)
    )
    approval_id = analyzed.json()["approval"]["approval_id"]
    client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)

    first = client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=PROCUREMENT)
    second = client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=PROCUREMENT)

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["ticket_id"] == second.json()["ticket_id"]
    assert second.json()["status"] == "ALREADY_PROCESSED"


def test_persistent_mockdesk_store_survives_new_application_instance(tmp_path: Path) -> None:
    # Revision tracking lives in the application store: a pending approval is only reused
    # or superseded within the store that recorded its request fingerprint. A second
    # application store therefore opens a new approval and a new ticket for the same input.
    shared_mockdesk = tmp_path / "shared-mockdesk.db"

    first_run = build_client(tmp_path / "run1", mockdesk_db=shared_mockdesk)
    first = analyze_approve_execute(first_run, hero_payload(received_quotes=1))

    second_run = build_client(tmp_path / "run2", mockdesk_db=shared_mockdesk)
    second = analyze_approve_execute(second_run, hero_payload(received_quotes=1))

    assert first["status"] == "OPEN"
    assert second["status"] == "OPEN"
    assert second["ticket_id"] != first["ticket_id"]
