import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway
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


def build_service(tmp_path: Path) -> tuple[ProcurementService, Path]:
    suppliers = tmp_path / "suppliers.csv"
    shutil.copyfile(ROOT / "data" / "suppliers.csv", suppliers)
    service = ProcurementService(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        policy_repository=PolicyRepository(ROOT / "data" / "documents.json"),
        policy_engine=PolicyEngine.from_yaml(ROOT / "data" / "policy_rules.yaml"),
        suppliers_path=suppliers,
        purchase_history_path=ROOT / "data" / "purchase_history.csv",
    )
    return service, suppliers


def analyze(client: TestClient) -> dict:
    response = client.post("/api/v1/requests/analyze", headers=PROCUREMENT, json=HERO_REQUEST)
    assert response.status_code == 200
    return response.json()


def test_changed_decision_inputs_supersede_the_approved_approval(tmp_path: Path) -> None:
    service, suppliers = build_service(tmp_path)
    client = TestClient(create_app(service=service))

    first = analyze(client)
    first_id = first["approval"]["approval_id"]
    assert "SUPPLIER_CERTIFICATE" in first["decision"]["applicable_rule_ids"]
    approved = client.post(f"/api/v1/approvals/{first_id}/approve", headers=FINANCE)
    assert approved.status_code == 200

    # The supplier renews its certificate before execution: the decision context changes
    # while the raw purchase request stays byte-identical.
    suppliers.write_text(
        suppliers.read_text(encoding="utf-8").replace("2026-06-30", "2027-12-31"),
        encoding="utf-8",
    )
    second = analyze(client)

    assert "SUPPLIER_CERTIFICATE" not in second["decision"]["applicable_rule_ids"]
    second_id = second["approval"]["approval_id"]
    assert second_id != first_id, "changed decision context must not reuse the old approval"

    stale_execute = client.post(f"/api/v1/tool-actions/{first_id}/execute", headers=PROCUREMENT)
    assert stale_execute.status_code == 409

    assert client.post(f"/api/v1/approvals/{second_id}/approve", headers=FINANCE).status_code == 200
    fresh_execute = client.post(f"/api/v1/tool-actions/{second_id}/execute", headers=PROCUREMENT)
    assert fresh_execute.status_code == 200
    assert fresh_execute.json()["status"] == "OPEN"


def test_identical_reanalysis_preserves_the_approved_case_snapshot(tmp_path: Path) -> None:
    service, _suppliers = build_service(tmp_path)
    client = TestClient(create_app(service=service))

    first = analyze(client)
    approval_id = first["approval"]["approval_id"]
    first_trace = first["trace_id"]
    approved = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)
    assert approved.status_code == 200

    second = analyze(client)
    assert second["approval"]["approval_id"] == approval_id
    assert second["trace_id"] != first_trace

    executed = client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=PROCUREMENT)
    assert executed.status_code == 200
    events = client.get("/api/v1/audit/events", headers=AUDIT).json()
    tool_events = [event for event in events if event["event_type"] == "TOOL_EXECUTED"]
    assert len(tool_events) == 1
    assert tool_events[0]["trace_id"] == first_trace, (
        "execution must run under the approved case snapshot, not a later overwrite"
    )


def test_tampered_case_snapshot_blocks_execution(tmp_path: Path) -> None:
    service, _suppliers = build_service(tmp_path)
    client = TestClient(create_app(service=service))

    first = analyze(client)
    approval_id = first["approval"]["approval_id"]
    approved = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=FINANCE)
    assert approved.status_code == 200

    case = service.store.load_case(approval_id)
    case["decision"]["blocking_reasons"] = ["Tampered reason"]
    service.store.save_case(approval_id, case)

    executed = client.post(f"/api/v1/tool-actions/{approval_id}/execute", headers=PROCUREMENT)

    assert executed.status_code == 409
    assert executed.json()["error"]["code"] == "APPROVAL_CONTEXT_CHANGED"
    events = client.get("/api/v1/audit/events", headers=AUDIT).json()
    blocked = [event for event in events if event["event_type"] == "TOOL_EXECUTION_BLOCKED"]
    assert len(blocked) == 1
