from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway
from app.models import PurchaseAnalysis, PurchaseRequest, SupplierRecord
from app.policy_engine import PolicyEngine
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore

ROOT = Path(__file__).resolve().parents[1]
PROCUREMENT_HEADERS = {
    "X-Demo-Role": "procurement_specialist",
    "X-Demo-User": "procurement_user",
}
AUDIT_HEADERS = {
    "X-Demo-Role": "solution_engineer",
    "X-Demo-User": "solution_engineer",
}

NEUTRAL_ANALYSIS = PurchaseAnalysis(
    historical_median_try=Decimal("100000"),
    variance_percent=Decimal("0"),
    display_variance_percent=Decimal("0"),
    standard_lead_time_days=14,
    lead_time_variance_days=0,
)


def build_client(tmp_path: Path) -> TestClient:
    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        project_root=ROOT,
    )
    return TestClient(create_app(service=service))


def _suspended_supplier() -> SupplierRecord:
    return SupplierRecord(
        supplier_name="Vega Hidrolik",
        quality_score=58,
        iso_9001_expiry_date=date(2027, 1, 15),
        status="suspended",
        risk_flag="blacklist",
    )


def _request(amount_try: str, received_quotes: int) -> PurchaseRequest:
    return PurchaseRequest(
        request_id="PR-2026-0090",
        request_date="2026-08-18",
        supplier_name="Vega Hidrolik",
        category="SPARE_PARTS",
        amount_try=amount_try,
        received_quotes=received_quotes,
        offered_lead_time_days=14,
    )


def test_suspended_supplier_is_rejected_even_below_all_thresholds() -> None:
    decision = PolicyEngine.from_yaml(ROOT / "data/policy_rules.yaml").evaluate(
        request=_request("90000", 2),
        analysis=NEUTRAL_ANALYSIS,
        supplier=_suspended_supplier(),
    )

    assert decision.decision_status == "REJECTED"
    assert "SUPPLIER_STATUS" in decision.applicable_rule_ids
    assert decision.finance_approval_required is False
    assert decision.blocking_reasons


def test_rejection_wins_over_conditional_review() -> None:
    decision = PolicyEngine.from_yaml(ROOT / "data/policy_rules.yaml").evaluate(
        request=_request("220000", 1),
        analysis=NEUTRAL_ANALYSIS,
        supplier=_suspended_supplier(),
    )

    assert decision.decision_status == "REJECTED"
    assert decision.finance_approval_required is True
    assert {"FINANCE_APPROVAL", "SUPPLIER_STATUS"} <= set(decision.applicable_rule_ids)


def test_rejected_analysis_creates_no_approval_and_cites_eligibility(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    payload = {
        "request_id": "PR-2026-0090",
        "request_date": "2026-08-18",
        "supplier_name": "Vega Hidrolik",
        "category": "SPARE_PARTS",
        "amount_try": "220000",
        "received_quotes": 1,
        "offered_lead_time_days": 14,
    }

    response = client.post("/api/v1/requests/analyze", headers=PROCUREMENT_HEADERS, json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["decision_status"] == "REJECTED"
    assert body["approval"] is None
    assert ("SUP-COMP-2026", "2.1") in [
        (item["document_id"], item["section_id"]) for item in body["citations"]
    ]


def test_rejected_reanalysis_supersedes_previous_pending_approval(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    conditional_payload = {
        "request_id": "PR-2026-0091",
        "request_date": "2026-08-18",
        "supplier_name": "Atlas Endüstri",
        "category": "SPARE_PARTS",
        "amount_try": "220000",
        "received_quotes": 1,
        "offered_lead_time_days": 20,
    }
    first = client.post(
        "/api/v1/requests/analyze", headers=PROCUREMENT_HEADERS, json=conditional_payload
    )
    assert first.json()["approval"] is not None
    previous_approval_id = first.json()["approval"]["approval_id"]

    rejected_payload = dict(conditional_payload, supplier_name="Vega Hidrolik")
    second = client.post(
        "/api/v1/requests/analyze", headers=PROCUREMENT_HEADERS, json=rejected_payload
    )

    assert second.status_code == 200
    assert second.json()["decision"]["decision_status"] == "REJECTED"
    assert second.json()["approval"] is None
    audit = client.get("/api/v1/audit/events", headers=AUDIT_HEADERS).json()
    superseded = [
        event for event in audit if event["event_type"] == "APPROVAL_SUPERSEDED"
    ]
    assert [event["approval_id"] for event in superseded] == [previous_approval_id]
