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


def build_client(tmp_path: Path) -> TestClient:
    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        project_root=ROOT,
    )
    return TestClient(create_app(service=service))


def run_exception_path(client: TestClient, payload: dict, expected_rules: list[str]) -> None:
    analyzed = client.post("/api/v1/requests/analyze", headers=PROCUREMENT, json=payload)
    assert analyzed.status_code == 200
    body = analyzed.json()
    assert body["decision"]["decision_status"] == "CONDITIONAL_REVIEW"
    assert body["decision"]["applicable_rule_ids"] == expected_rules

    approval = body["approval"]
    assert approval is not None, "blocking decision must create an actionable approval"
    assert approval["required_role"] == "finance_approver"
    approval_id = approval["approval_id"]

    preview = client.get(
        f"/api/v1/approvals/{approval_id}/action-preview", headers=PROCUREMENT
    )
    assert preview.status_code == 200
    assert preview.json()["required_role"] == "finance_approver"

    approved = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)
    assert approved.status_code == 200

    executed = client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=PROCUREMENT)
    assert executed.status_code == 200
    assert executed.json()["status"] == "OPEN"


def test_quote_only_exception_is_actionable(tmp_path: Path) -> None:
    run_exception_path(
        build_client(tmp_path),
        {
            "request_id": "PR-2026-QUOTE",
            "request_date": "2026-08-18",
            "supplier_name": "Ege Parça",
            "category": "SPARE_PARTS",
            "amount_try": "150000",
            "received_quotes": 1,
            "offered_lead_time_days": 10,
        },
        expected_rules=["ALTERNATIVE_QUOTES"],
    )


def test_certificate_only_exception_is_actionable(tmp_path: Path) -> None:
    run_exception_path(
        build_client(tmp_path),
        {
            "request_id": "PR-2026-CERT",
            "request_date": "2026-08-18",
            "supplier_name": "Atlas Endüstri",
            "category": "SPARE_PARTS",
            "amount_try": "90000",
            "received_quotes": 2,
            "offered_lead_time_days": 10,
        },
        expected_rules=["SUPPLIER_CERTIFICATE"],
    )
