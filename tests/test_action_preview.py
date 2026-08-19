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


class RecordingMockDeskGateway:
    def __init__(self, store: MockDeskStore) -> None:
        self._inner = InProcessMockDeskGateway(store)
        self.calls: list[tuple[dict[str, object], str]] = []

    def create_ticket(self, payload: dict[str, object], idempotency_key: str):
        self.calls.append((payload, idempotency_key))
        return self._inner.create_ticket(payload, idempotency_key)


def build_client(tmp_path: Path) -> tuple[TestClient, RecordingMockDeskGateway]:
    gateway = RecordingMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db"))
    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=gateway,
        project_root=Path.cwd(),
    )
    return TestClient(create_app(service=service)), gateway


def analyze_hero_request(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/requests/analyze",
        headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"},
        json=HERO_REQUEST,
    )
    assert response.status_code == 200
    return response.json()


def test_action_preview_returns_server_generated_outbound_action(tmp_path: Path) -> None:
    client, _gateway = build_client(tmp_path)
    approval_id = analyze_hero_request(client)["approval"]["approval_id"]

    response = client.get(
        f"/api/v1/approvals/{approval_id}/action-preview",
        headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"},
    )

    assert response.status_code == 200
    preview = response.json()
    assert preview["approval_id"] == approval_id
    assert preview["target_system"] == "MOCKDESK"
    assert preview["operation"] == "CREATE_PROCUREMENT_EXCEPTION_TICKET"
    assert preview["idempotency_key"] == f"{approval_id}-CREATE_PROCUREMENT_EXCEPTION_TICKET"
    assert preview["required_role"] == "finance_approver"
    assert preview["payload"]["request_id"] == "PR-2026-0042"
    assert preview["payload"]["summary"] == "Procurement Exception Review"
    assert preview["payload"]["decision_status"] == "CONDITIONAL_REVIEW"


def test_action_preview_for_unknown_approval_returns_404(tmp_path: Path) -> None:
    client, _gateway = build_client(tmp_path)

    response = client.get(
        "/api/v1/approvals/AP-DOES-NOT-EXIST/action-preview",
        headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"},
    )

    assert response.status_code == 404


def test_execute_sends_exactly_the_previewed_payload(tmp_path: Path) -> None:
    client, gateway = build_client(tmp_path)
    approval_id = analyze_hero_request(client)["approval"]["approval_id"]

    preview = client.get(
        f"/api/v1/approvals/{approval_id}/action-preview",
        headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"},
    ).json()
    approved = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-Demo-Role": "finance_approver", "X-Demo-User": "finance_user"},
    )
    assert approved.status_code == 200
    executed = client.post(
        f"/api/v1/tool-actions/{approval_id}/execute",
        headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"},
    )

    assert executed.status_code == 200
    assert gateway.calls == [(preview["payload"], preview["idempotency_key"])]
