from __future__ import annotations

import csv
import json
import re
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import median

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.analysis import analyze_purchase_history  # noqa: E402
from app.errors import ApplicablePolicyNotFoundError  # noqa: E402
from app.main import create_app  # noqa: E402
from app.mockdesk_client import InProcessMockDeskGateway  # noqa: E402
from app.models import PurchaseRequest  # noqa: E402
from app.retrieval import PolicyRepository  # noqa: E402
from app.service import ProcurementService  # noqa: E402
from app.store import SQLiteStore  # noqa: E402
from mockdesk.store import MockDeskStore  # noqa: E402


def check_history_median() -> None:
    amounts: list[Decimal] = []
    with (ROOT / "data/purchase_history.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["category"] == "SPARE_PARTS" and row["status"] == "COMPLETED":
                amounts.append(Decimal(row["amount_try"]))
    actual = Decimal(median(amounts))
    assert actual == Decimal("184500"), f"Unexpected SPARE_PARTS median: {actual}"


def check_backdated_history_boundary() -> None:
    request = PurchaseRequest(
        request_id="PR-2025-0618",
        request_date="2025-06-18",
        supplier_name="Atlas Endüstri",
        category="SPARE_PARTS",
        amount_try="180000",
        received_quotes=2,
        offered_lead_time_days=14,
    )
    result = analyze_purchase_history(request, ROOT / "data/purchase_history.csv")
    assert result.historical_median_try == Decimal("152500")


def check_policy_selection() -> None:
    repository = PolicyRepository(ROOT / "data/documents.json")
    current = repository.current_policy(
        policy_type="PROCUREMENT_POLICY",
        on_date=date(2026, 8, 18),
        role="procurement_specialist",
    )
    assert current.document_id == "PROC-POL-2026"
    assert current.status == "CURRENT"
    try:
        repository.current_policy(
            policy_type="PROCUREMENT_POLICY",
            on_date=date(2025, 8, 1),
            role="procurement_specialist",
        )
    except ApplicablePolicyNotFoundError:
        pass
    else:
        raise AssertionError("out-of-window request dates must not resolve a policy")


def check_policy_rule_alignment() -> None:
    rules = yaml.safe_load((ROOT / "data/policy_rules.yaml").read_text(encoding="utf-8"))
    policy = (ROOT / "data/procurement_policy_2026_current.md").read_text(encoding="utf-8")
    finance = re.search(r"([0-9.]+) TL üzerindeki satın alma talepleri", policy)
    quotes = re.search(r"([0-9.]+) TL üzerindeki satın almalarda en az (\w+) geçerli", policy)
    assert finance and quotes
    assert int(finance.group(1).replace(".", "")) == rules["finance_approval"]["threshold_try"]
    assert int(quotes.group(1).replace(".", "")) == rules["alternative_quotes"]["threshold_try"]
    assert {"bir": 1, "iki": 2, "üç": 3}[quotes.group(2).lower()] == rules[
        "alternative_quotes"
    ]["minimum_quotes"]


def check_json_and_jsonl() -> None:
    json.loads((ROOT / "data/documents.json").read_text(encoding="utf-8"))
    json.loads((ROOT / "data/example_request.json").read_text(encoding="utf-8"))
    for path in (ROOT / "evals").glob("*.jsonl"):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AssertionError(f"Invalid JSONL {path}:{line_number}") from exc


def check_browser_and_docker_hardening() -> None:
    script = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert ".innerHTML" not in script
    dockerignore = set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())
    assert {".git", ".venv", ".env", ".env.*", "runtime/", "reports/"} <= dockerignore


def check_hero_api_flow() -> None:
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        service = ProcurementService.from_project_data(
            store=SQLiteStore(temp / "valuebridge.db"),
            mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(temp / "mockdesk.db")),
            project_root=ROOT,
        )
        client = TestClient(create_app(service=service))
        payload = json.loads((ROOT / "data/example_request.json").read_text(encoding="utf-8"))
        analysis = client.post(
            "/api/v1/requests/analyze",
            headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "verify"},
            json=payload,
        )
        assert analysis.status_code == 200, analysis.text
        body = analysis.json()
        assert body["analysis"]["historical_median_try"] == "184500"
        assert body["analysis"]["variance_percent"] == "19.2412"
        assert body["decision"]["decision_status"] == "CONDITIONAL_REVIEW"
        assert body["approval"] is not None
        approval_id = body["approval"]["approval_id"]
        blocked = client.post(
            f"/api/v1/tool-actions/{approval_id}/execute",
            headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "verify"},
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "APPROVAL_REQUIRED"
        approved = client.post(
            f"/api/v1/approvals/{approval_id}/approve",
            headers={"X-Demo-Role": "finance_approver", "X-Demo-User": "finance_verify"},
        )
        assert approved.status_code == 200
        first = client.post(
            f"/api/v1/tool-actions/{approval_id}/execute",
            headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "verify"},
        ).json()
        second = client.post(
            f"/api/v1/tool-actions/{approval_id}/execute",
            headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "verify"},
        ).json()
        assert first["ticket_id"] == second["ticket_id"]
        assert second["status"] == "ALREADY_PROCESSED"


def main() -> None:
    checks = [
        ("history median", check_history_median),
        ("backdated history boundary", check_backdated_history_boundary),
        ("effective policy selection", check_policy_selection),
        ("policy-rule alignment", check_policy_rule_alignment),
        ("JSON and JSONL", check_json_and_jsonl),
        ("browser and Docker hardening", check_browser_and_docker_hardening),
        ("hero API flow", check_hero_api_flow),
    ]
    for name, check in checks:
        check()
        print(f"PASS: {name}")
    print(f"PASS: {len(checks)} project verification checks")


if __name__ == "__main__":
    main()
