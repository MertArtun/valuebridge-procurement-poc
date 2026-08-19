from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.errors import AuthorizationError
from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore

ROOT = Path(__file__).resolve().parents[1]
PROCUREMENT = {"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"}
FINANCE = {"X-Demo-Role": "finance_approver", "X-Demo-User": "finance_user"}
EXCEPTION_REQUEST = {
    "request_id": "PR-2026-QUOTE",
    "request_date": "2026-08-18",
    "supplier_name": "Ege Parça",
    "category": "SPARE_PARTS",
    "amount_try": "150000",
    "received_quotes": 1,
    "offered_lead_time_days": 10,
}


def build_client(tmp_path: Path) -> TestClient:
    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        project_root=ROOT,
    )
    return TestClient(create_app(service=service))


def test_approval_enforces_the_role_recorded_on_the_approval(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "valuebridge.db")
    approval = store.create_approval(
        request_id="PR-2026-0042",
        action_type="CREATE_PROCUREMENT_EXCEPTION_TICKET",
        requested_by="procurement_user",
        required_role="compliance_test_role",
    )

    with pytest.raises(AuthorizationError):
        store.approve(
            approval_id=approval.approval_id,
            approved_by="finance_user",
            approver_role="finance_approver",
        )

    assert store.get_approval(approval.approval_id).status == "PENDING"


def test_rejection_enforces_the_role_recorded_on_the_approval(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "valuebridge.db")
    approval = store.create_approval(
        request_id="PR-2026-0042",
        action_type="CREATE_PROCUREMENT_EXCEPTION_TICKET",
        requested_by="procurement_user",
        required_role="compliance_test_role",
    )

    with pytest.raises(AuthorizationError):
        store.reject(approval.approval_id, approver_role="finance_approver")

    assert store.get_approval(approval.approval_id).status == "PENDING"


def test_finance_approver_still_approves_a_finance_approval(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    analyzed = client.post(
        "/api/v1/requests/analyze", headers=PROCUREMENT, json=EXCEPTION_REQUEST
    )
    approval_id = analyzed.json()["approval"]["approval_id"]

    approved = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)

    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
