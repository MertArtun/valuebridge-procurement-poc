from __future__ import annotations

import os
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.analysis import analyze_purchase_history
from app.errors import ValueBridgeError
from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway
from app.models import PolicyDecision, PurchaseRequest
from app.retrieval import PolicyRepository
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


def build_client(tmp_path: Path) -> TestClient:
    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        project_root=ROOT,
    )
    return TestClient(create_app(service=service))


def test_request_id_rejects_markup() -> None:
    with pytest.raises(ValidationError):
        PurchaseRequest(
            request_id='PR-<img src=x onerror=alert(1)>',
            request_date="2026-08-18",
            supplier_name="Atlas Endüstri",
            category="SPARE_PARTS",
            amount_try="220000",
            received_quotes=1,
            offered_lead_time_days=20,
        )


def test_backdated_analysis_excludes_future_purchases() -> None:
    request = PurchaseRequest(
        request_id="PR-2025-0618",
        request_date="2025-06-18",
        supplier_name="Atlas Endüstri",
        category="SPARE_PARTS",
        amount_try="180000",
        received_quotes=2,
        offered_lead_time_days=14,
    )

    result = analyze_purchase_history(request, ROOT / "data" / "purchase_history.csv")

    assert result.historical_median_try == Decimal("152500")


def test_out_of_window_request_date_fails_with_explicit_policy_error(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    payload = {
        "request_id": "PR-2025-0618",
        "request_date": "2025-06-18",
        "supplier_name": "Atlas Endüstri",
        "category": "SPARE_PARTS",
        "amount_try": "180000",
        "received_quotes": 2,
        "offered_lead_time_days": 14,
    }

    response = client.post("/api/v1/requests/analyze", headers=PROCUREMENT_HEADERS, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "APPLICABLE_POLICY_NOT_FOUND"
    assert "PROCUREMENT_POLICY" in response.json()["error"]["message"]


def test_missing_cited_section_raises_structured_error_not_keyerror() -> None:
    repository = PolicyRepository(ROOT / "data" / "documents.json")
    superseded = next(
        entry
        for entry in repository.searchable_documents("procurement_specialist")
        if entry.document_id == "PROC-POL-2025"
    )
    no_rule_decision = PolicyDecision(
        decision_status="APPROVED",
        finance_approval_required=False,
        alternative_quote_missing=False,
        certificate_status="VALID",
        lead_time_variance_days=0,
        blocking_reasons=[],
        warnings=[],
        applicable_rule_ids=[],
    )

    with pytest.raises(ValueBridgeError):
        ProcurementService._build_citations(
            no_rule_decision,
            {"PROCUREMENT_POLICY": superseded, "SUPPLIER_COMPLIANCE_POLICY": superseded},
        )


def test_unknown_supplier_returns_structured_error_and_audits_failure(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    payload = {
        "request_id": "PR-2026-UNKNOWN",
        "request_date": "2026-08-18",
        "supplier_name": "Missing Supplier",
        "category": "SPARE_PARTS",
        "amount_try": "220000",
        "received_quotes": 1,
        "offered_lead_time_days": 20,
    }

    response = client.post("/api/v1/requests/analyze", headers=PROCUREMENT_HEADERS, json=payload)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SUPPLIER_NOT_FOUND"
    assert response.json()["error"]["trace_id"].startswith("trace-")
    audit = client.get("/api/v1/audit/events", headers=AUDIT_HEADERS).json()
    failed = [event for event in audit if event["event_type"] == "ANALYSIS_FAILED"]
    assert len(failed) == 1
    assert failed[0]["details"]["code"] == "SUPPLIER_NOT_FOUND"


def test_low_risk_request_does_not_create_finance_approval(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    payload = {
        "request_id": "PR-2026-LOW-RISK",
        "request_date": "2026-08-18",
        "supplier_name": "Ege Parça",
        "category": "OFFICE_SUPPLIES",
        "amount_try": "90000",
        "received_quotes": 2,
        "offered_lead_time_days": 5,
    }

    response = client.post("/api/v1/requests/analyze", headers=PROCUREMENT_HEADERS, json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["decision_status"] == "APPROVED"
    assert body["approval"] is None
    assert [(item["document_id"], item["section_id"]) for item in body["citations"]] == [
        ("PROC-POL-2026", "4.1")
    ]


def test_policy_markdown_matches_runtime_thresholds() -> None:
    rules = yaml.safe_load((ROOT / "data" / "policy_rules.yaml").read_text(encoding="utf-8"))
    policy = (ROOT / "data" / "procurement_policy_2026_current.md").read_text(
        encoding="utf-8"
    )
    finance = re.search(r"([0-9.]+) TL üzerindeki satın alma talepleri", policy)
    quotes = re.search(r"([0-9.]+) TL üzerindeki satın almalarda en az (\w+) geçerli", policy)

    assert finance is not None
    assert quotes is not None
    finance_value = int(finance.group(1).replace(".", ""))
    quote_value = int(quotes.group(1).replace(".", ""))
    quote_words = {"bir": 1, "iki": 2, "üç": 3}
    assert finance_value == rules["finance_approval"]["threshold_try"]
    assert quote_value == rules["alternative_quotes"]["threshold_try"]
    assert quote_words[quotes.group(2).lower()] == rules["alternative_quotes"]["minimum_quotes"]


def test_importing_app_main_does_not_create_runtime_database(tmp_path: Path) -> None:
    db_path = tmp_path / "import-side-effect.db"
    env = os.environ.copy()
    env["VALUEBRIDGE_DB_PATH"] = str(db_path)
    subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=ROOT,
        env=env,
        check=True,
    )

    assert not db_path.exists()


def test_home_sets_browser_security_headers(tmp_path: Path) -> None:
    response = build_client(tmp_path).get("/")

    assert response.status_code == 200
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
