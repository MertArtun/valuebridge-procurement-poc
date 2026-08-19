import shutil
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.errors import MockDeskRequestError
from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway, _response_error_message
from app.policy_engine import PolicyEngine
from app.retrieval import PolicyRepository
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore

ROOT = Path(__file__).resolve().parents[1]
PROCUREMENT = {"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"}
FINANCE = {"X-Demo-Role": "finance_approver", "X-Demo-User": "finance_user"}
AUDIT = {"X-Demo-Role": "solution_engineer", "X-Demo-User": "solution_engineer"}

HERO_REQUEST = {
    "request_id": "PR-2026-0042",
    "request_date": "2026-08-18",
    "supplier_name": "Atlas Endüstri",
    "category": "SPARE_PARTS",
    "amount_try": "220000",
    "received_quotes": 1,
    "offered_lead_time_days": 20,
}


def build_client(tmp_path: Path, *, gateway=None, history_path: Path | None = None) -> TestClient:
    service = ProcurementService(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=gateway
        or InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        policy_repository=PolicyRepository(ROOT / "data" / "documents.json"),
        policy_engine=PolicyEngine.from_yaml(ROOT / "data" / "policy_rules.yaml"),
        suppliers_path=ROOT / "data" / "suppliers.csv",
        purchase_history_path=history_path or (ROOT / "data" / "purchase_history.csv"),
    )
    return TestClient(create_app(service=service))


def audit_events(client: TestClient) -> list[dict]:
    response = client.get("/api/v1/audit/events", headers=AUDIT)
    assert response.status_code == 200
    return response.json()


def test_nonretryable_mockdesk_failure_returns_traced_502_and_is_audited(
    tmp_path: Path,
) -> None:
    class BrokenGateway:
        def create_ticket(self, payload: dict[str, object], idempotency_key: str):
            raise MockDeskRequestError("MockDesk returned HTTP 500: internal error")

    client = build_client(tmp_path, gateway=BrokenGateway())
    analyzed = client.post("/api/v1/requests/analyze", headers=PROCUREMENT, json=HERO_REQUEST)
    approval_id = analyzed.json()["approval"]["approval_id"]
    approved = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)
    assert approved.status_code == 200

    response = client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=PROCUREMENT)

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "MOCKDESK_REQUEST_FAILED"
    assert error["trace_id"] is not None and error["trace_id"].startswith("trace-")
    failed = [e for e in audit_events(client) if e["event_type"] == "TOOL_EXECUTION_FAILED"]
    assert len(failed) == 1
    assert failed[0]["approval_id"] == approval_id


def test_denied_analysis_is_audited_as_authorization_denied(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    response = client.post(
        "/api/v1/requests/analyze",
        headers={"X-Demo-Role": "auditor", "X-Demo-User": "mallory"},
        json=HERO_REQUEST,
    )

    assert response.status_code == 403
    assert response.json()["error"]["trace_id"].startswith("trace-")
    events = audit_events(client)
    denied = [e for e in events if e["event_type"] == "AUTHORIZATION_DENIED"]
    assert len(denied) == 1
    assert denied[0]["actor"] == "mallory"
    assert not [e for e in events if e["event_type"] == "ANALYSIS_FAILED"]


def _history_with_extra_row(tmp_path: Path, row: str) -> Path:
    history = tmp_path / "purchase_history.csv"
    shutil.copyfile(ROOT / "data" / "purchase_history.csv", history)
    with history.open("a", encoding="utf-8") as handle:
        handle.write(row + "\n")
    return history


def test_malformed_row_in_unrelated_category_does_not_break_analysis(tmp_path: Path) -> None:
    history = _history_with_extra_row(
        tmp_path, "PO-9099,,Delta Endüstri,OFFICE_SUPPLIES,50000,10,CANCELLED"
    )
    client = build_client(tmp_path, history_path=history)

    response = client.post("/api/v1/requests/analyze", headers=PROCUREMENT, json=HERO_REQUEST)

    assert response.status_code == 200
    assert response.json()["analysis"]["historical_median_try"] == "184500"


def test_malformed_row_in_relevant_category_raises_structured_error(tmp_path: Path) -> None:
    history = _history_with_extra_row(
        tmp_path, "PO-9100,not-a-date,Atlas Endüstri,SPARE_PARTS,120000,10,COMPLETED"
    )
    client = build_client(tmp_path, history_path=history)

    response = client.post("/api/v1/requests/analyze", headers=PROCUREMENT, json=HERO_REQUEST)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PURCHASE_HISTORY_INVALID"


def test_malformed_amount_in_relevant_category_raises_structured_error(tmp_path: Path) -> None:
    history = _history_with_extra_row(
        tmp_path, "PO-9101,2026-01-15,Atlas Endüstri,SPARE_PARTS,not-a-number,10,COMPLETED"
    )
    client = build_client(tmp_path, history_path=history)

    response = client.post("/api/v1/requests/analyze", headers=PROCUREMENT, json=HERO_REQUEST)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PURCHASE_HISTORY_INVALID"


def test_mockdesk_validation_detail_is_sanitized() -> None:
    secret_input = "S" * 300
    response = httpx.Response(
        422,
        json={
            "detail": [
                {
                    "type": "string_too_long",
                    "loc": ["body", "summary"],
                    "msg": "String should have at most 240 characters",
                    "input": secret_input,
                }
            ]
        },
        request=httpx.Request("POST", "http://mockdesk/tickets"),
    )

    message = _response_error_message(response)

    assert secret_input not in message
    assert "summary" in message
    assert "String should have at most 240 characters" in message
