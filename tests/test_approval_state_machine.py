from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore

HERO_REQUEST = {
    "request_id": "PR-2026-0042",
    "request_date": "2026-08-18",
    "supplier_name": "Atlas Endüstri",
    "category": "SPARE_PARTS",
    "amount_try": "220000",
    "received_quotes": 1,
    "offered_lead_time_days": 20,
}

PROCUREMENT = {"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"}
FINANCE = {"X-Demo-Role": "finance_approver", "X-Demo-User": "finance_user"}


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)

    def advance(self, delta: timedelta) -> None:
        self.current += delta

    def __call__(self) -> datetime:
        return self.current


def build_client(tmp_path: Path) -> tuple[TestClient, FakeClock]:
    clock = FakeClock()
    store = SQLiteStore(tmp_path / "valuebridge.db", now=clock)
    mockdesk = InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db"))
    service = ProcurementService.from_project_data(
        store=store,
        mockdesk_gateway=mockdesk,
        project_root=Path.cwd(),
    )
    return TestClient(create_app(service=service)), clock


def create_pending_approval(client: TestClient) -> str:
    response = client.post("/api/v1/requests/analyze", headers=PROCUREMENT, json=HERO_REQUEST)
    assert response.status_code == 200
    return response.json()["approval"]["approval_id"]


def audit_event_types(client: TestClient) -> list[str]:
    response = client.get("/api/v1/audit/events", headers=FINANCE)
    assert response.status_code == 200
    return [event["event_type"] for event in response.json()]


def test_pending_approval_can_be_rejected_by_finance(tmp_path: Path) -> None:
    client, _clock = build_client(tmp_path)
    approval_id = create_pending_approval(client)

    response = client.post(f"/api/v1/approvals/{approval_id}/reject", headers=FINANCE)

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "APPROVAL_REJECTED" in audit_event_types(client)


def test_only_finance_role_may_reject(tmp_path: Path) -> None:
    client, _clock = build_client(tmp_path)
    approval_id = create_pending_approval(client)

    response = client.post(f"/api/v1/approvals/{approval_id}/reject", headers=PROCUREMENT)

    assert response.status_code == 403


def test_rejected_approval_cannot_be_approved(tmp_path: Path) -> None:
    client, _clock = build_client(tmp_path)
    approval_id = create_pending_approval(client)
    rejected = client.post(f"/api/v1/approvals/{approval_id}/reject", headers=FINANCE)
    assert rejected.status_code == 200

    response = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)

    assert response.status_code == 409


def test_approved_approval_cannot_be_rejected(tmp_path: Path) -> None:
    client, _clock = build_client(tmp_path)
    approval_id = create_pending_approval(client)
    approved = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)
    assert approved.status_code == 200

    response = client.post(f"/api/v1/approvals/{approval_id}/reject", headers=FINANCE)

    assert response.status_code == 409


def test_approved_approval_cannot_be_approved_again(tmp_path: Path) -> None:
    client, _clock = build_client(tmp_path)
    approval_id = create_pending_approval(client)
    approved = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)
    assert approved.status_code == 200

    response = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)

    assert response.status_code == 409


def test_rejected_approval_blocks_execution(tmp_path: Path) -> None:
    client, _clock = build_client(tmp_path)
    approval_id = create_pending_approval(client)
    rejected = client.post(f"/api/v1/approvals/{approval_id}/reject", headers=FINANCE)
    assert rejected.status_code == 200

    response = client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=PROCUREMENT)

    assert response.status_code == 409


def test_pending_approval_expires_after_ttl(tmp_path: Path) -> None:
    client, clock = build_client(tmp_path)
    approval_id = create_pending_approval(client)

    clock.advance(timedelta(hours=25))
    response = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)

    assert response.status_code == 409
    assert "APPROVAL_EXPIRED" in audit_event_types(client)


def test_expired_approval_cannot_be_rejected(tmp_path: Path) -> None:
    client, clock = build_client(tmp_path)
    approval_id = create_pending_approval(client)

    clock.advance(timedelta(hours=25))
    response = client.post(f"/api/v1/approvals/{approval_id}/reject", headers=FINANCE)

    assert response.status_code == 409


def test_reanalysis_after_ttl_expires_the_stale_approval(tmp_path: Path) -> None:
    client, clock = build_client(tmp_path)
    stale_id = create_pending_approval(client)

    clock.advance(timedelta(hours=25))
    renewed_id = create_pending_approval(client)

    assert renewed_id != stale_id
    assert "APPROVAL_EXPIRED" in audit_event_types(client)
    stale = client.post(f"/api/v1/approvals/{stale_id}/approve", headers=FINANCE)
    renewed = client.post(f"/api/v1/approvals/{renewed_id}/approve", headers=FINANCE)
    assert stale.status_code == 409
    assert renewed.status_code == 200


def test_approval_within_ttl_still_succeeds(tmp_path: Path) -> None:
    client, clock = build_client(tmp_path)
    approval_id = create_pending_approval(client)

    clock.advance(timedelta(hours=23))
    response = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)

    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
