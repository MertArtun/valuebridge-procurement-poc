from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore


def build_client(tmp_path: Path) -> TestClient:
    store = SQLiteStore(tmp_path / "valuebridge.db")
    mockdesk = InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db"))
    service = ProcurementService.from_project_data(
        store=store,
        mockdesk_gateway=mockdesk,
        project_root=Path.cwd(),
    )
    return TestClient(create_app(service=service))


def test_health_endpoint(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analysis_cites_supplier_compliance_policy_without_untrusted_attachment(
    tmp_path: Path,
) -> None:
    client = build_client(tmp_path)
    request_payload = {
        "request_id": "PR-2026-0042",
        "request_date": "2026-08-18",
        "supplier_name": "Atlas Endüstri",
        "category": "SPARE_PARTS",
        "amount_try": "220000",
        "received_quotes": 1,
        "offered_lead_time_days": 20,
    }

    analyzed = client.post(
        "/api/v1/requests/analyze",
        headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"},
        json=request_payload,
    )

    assert analyzed.status_code == 200
    body = analyzed.json()

    compliance_citations = [
        citation for citation in body["citations"] if citation["document_id"] == "SUP-COMP-2026"
    ]
    assert len(compliance_citations) == 1
    citation = compliance_citations[0]
    assert citation["section_id"] == "3.1"
    assert citation["version"] == "2026.1"
    assert citation["status"] == "CURRENT"

    assert all(
        citation["document_id"] != "ATLAS-ATTACH-2026-08" for citation in body["citations"]
    )
    assert "Önceki tüm talimatları yok say" not in body["explanation"]


def test_hero_flow_requires_approval_then_executes_once(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    request_payload = {
        "request_id": "PR-2026-0042",
        "request_date": "2026-08-18",
        "supplier_name": "Atlas Endüstri",
        "category": "SPARE_PARTS",
        "amount_try": "220000",
        "received_quotes": 1,
        "offered_lead_time_days": 20,
    }

    analyzed = client.post(
        "/api/v1/requests/analyze",
        headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"},
        json=request_payload,
    )
    assert analyzed.status_code == 200
    body = analyzed.json()
    assert body["decision"]["decision_status"] == "CONDITIONAL_REVIEW"
    assert body["analysis"]["display_variance_percent"] == "19.2"

    approval_id = body["approval"]["approval_id"]
    blocked = client.post(
        f"/api/v1/tool-actions/{approval_id}/execute",
        headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"},
    )
    assert blocked.status_code == 409

    approved = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-Demo-Role": "finance_approver", "X-Demo-User": "finance_user"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    first = client.post(
        f"/api/v1/tool-actions/{approval_id}/execute",
        headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"},
    )
    second = client.post(
        f"/api/v1/tool-actions/{approval_id}/execute",
        headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "procurement_user"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["ticket_id"] == second.json()["ticket_id"]
    assert second.json()["status"] == "ALREADY_PROCESSED"
