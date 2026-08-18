from __future__ import annotations

import csv
import json
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.mockdesk_client import InProcessMockDeskGateway  # noqa: E402
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


def check_policy_selection() -> None:
    repository = PolicyRepository(ROOT / "data/documents.json")
    policy = repository.current_policy(
        policy_type="PROCUREMENT_POLICY",
        on_date=date(2026, 8, 18),
        role="procurement_specialist",
    )
    assert policy.document_id == "PROC-POL-2026"
    assert policy.status == "CURRENT"


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
        approval_id = body["approval"]["approval_id"]
        blocked = client.post(
            f"/api/v1/tool-actions/{approval_id}/execute",
            headers={"X-Demo-Role": "procurement_specialist", "X-Demo-User": "verify"},
        )
        assert blocked.status_code == 409
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
        ("current policy", check_policy_selection),
        ("JSON and JSONL", check_json_and_jsonl),
        ("hero API flow", check_hero_api_flow),
    ]
    for name, check in checks:
        check()
        print(f"PASS: {name}")
    print(f"PASS: {len(checks)} project verification checks")


if __name__ == "__main__":
    main()
