"""Deterministic evaluation runner for the frozen cases in ``evals/``.

Expected outcomes are derived here from ``evals/policy_oracle.yaml``, never from
the values the application components return. Security and retrieval cases are
not parameterized by the oracle file, so their frozen ``expected`` block is the
oracle for those cases. A case whose frozen ``expected`` block contradicts the
oracle fails as dataset drift, so corrupted cases can never report ``PASSED``.
"""

from __future__ import annotations

import json
import tempfile
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from app.models import PurchaseAnalysis, PurchaseRequest, SupplierRecord
from app.policy_engine import PolicyEngine
from app.policy_qa import PolicyQaService
from app.retrieval import PolicyRepository
from app.security import AuthorizationError, authorize, contains_prompt_injection
from mockdesk.store import MockDeskStore

_UNTRUSTED_DOCUMENT_ID = "ATLAS-ATTACH-2026-08"

_NEUTRAL_ANALYSIS = PurchaseAnalysis(
    historical_median_try=Decimal("0"),
    variance_percent=Decimal("0"),
    display_variance_percent=Decimal("0"),
    standard_lead_time_days=14,
    lead_time_variance_days=0,
)


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_evaluation(
    case_paths: Sequence[Path],
    *,
    oracle_path: Path,
    policy_rules_path: Path,
) -> dict[str, Any]:
    cases = [case for path in case_paths for case in load_cases(path)]
    with tempfile.TemporaryDirectory() as directory:
        runner = _CaseRunner(
            oracle=yaml.safe_load(oracle_path.read_text(encoding="utf-8")),
            engine=PolicyEngine.from_yaml(policy_rules_path),
            workspace=Path(directory),
            documents_path=policy_rules_path.parent / "documents.json",
        )
        results = [runner.run(case) for case in cases]

    passed = sum(1 for result in results if result["status"] == "PASSED")
    return {
        "run_id": uuid.uuid4().hex,
        "generated_at": datetime.now(UTC).isoformat(),
        "counts": {"passed": passed, "failed": len(results) - passed},
        "cases": results,
    }


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class _CaseRunner:
    def __init__(
        self,
        *,
        oracle: dict[str, Any],
        engine: PolicyEngine,
        workspace: Path,
        documents_path: Path,
    ) -> None:
        self._oracle = oracle
        self._engine = engine
        self._tickets = MockDeskStore(workspace / "mockdesk.db")
        self._documents_path = documents_path
        self._repository: PolicyRepository | None = None
        self._seen_keys: set[str] = set()
        self._expected_ticket_count = 0

    def run(self, case: dict[str, Any]) -> dict[str, Any]:
        try:
            expected, actual = self._execute(case)
            frozen = dict(case["expected"])
            if not frozen:
                raise ValueError("Case declares no expected fields")
            fields = list(frozen)
            expected = {field: expected[field] for field in fields}
            actual = {field: actual[field] for field in fields}
            differences = [
                f"{field}: frozen case {frozen[field]!r}, oracle {expected[field]!r}"
                for field in fields
                if frozen[field] != expected[field]
            ] + [
                f"{field}: expected {expected[field]!r}, actual {actual[field]!r}"
                for field in fields
                if expected[field] != actual[field]
            ]
            reason = "; ".join(differences) or None
        except Exception as error:  # preserved as a failed case, never dropped
            expected = case.get("expected", {})
            actual = {}
            reason = f"{type(error).__name__}: {error}"

        return {
            "case_id": case["case_id"],
            "description": case.get("description", ""),
            "severity": case.get("severity", "UNSPECIFIED"),
            "status": "FAILED" if reason else "PASSED",
            "expected": expected,
            "actual": actual,
            "reason": reason,
        }

    def _execute(self, case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        family = str(case["case_id"]).split("-", 1)[0]
        if family == "POL":
            return self._policy_case(case)
        if family == "SEC":
            return self._security_case(case)
        if family == "IDEM":
            return self._idempotency_case(case)
        if family == "RAG":
            return self._retrieval_case(case)
        raise ValueError(f"Unsupported case family {family!r}")

    def _policy_case(self, case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        data = case["input"]
        amount = Decimal(str(data["amount_try"]))
        received_quotes = int(data["received_quotes"])
        request_date = date.fromisoformat(data["request_date"])
        certificate_expiry = date.fromisoformat(data["certificate_expiry"])
        supplier_status = str(data.get("supplier_status", "active"))

        expected = self._policy_oracle(
            amount, received_quotes, request_date, certificate_expiry, supplier_status
        )
        decision = self._engine.evaluate(
            request=PurchaseRequest(
                request_id=case["case_id"],
                request_date=request_date,
                supplier_name="Evaluation Supplier",
                category="SPARE_PARTS",
                amount_try=amount,
                received_quotes=received_quotes,
                offered_lead_time_days=14,
            ),
            analysis=_NEUTRAL_ANALYSIS,
            supplier=SupplierRecord(
                supplier_name="Evaluation Supplier",
                quality_score=80,
                iso_9001_expiry_date=certificate_expiry,
                status=supplier_status,
                risk_flag="none",
            ),
        )
        actual = {
            "decision_status": decision.decision_status,
            "finance_approval_required": decision.finance_approval_required,
            "alternative_quote_missing": decision.alternative_quote_missing,
            "certificate_status": decision.certificate_status,
        }
        return expected, actual

    def _policy_oracle(
        self,
        amount: Decimal,
        received_quotes: int,
        request_date: date,
        certificate_expiry: date,
        supplier_status: str,
    ) -> dict[str, Any]:
        finance_rule = self._oracle["finance_approval"]
        if finance_rule["comparison"] != "greater_than":
            raise ValueError(f"Unsupported oracle comparison {finance_rule['comparison']!r}")
        quote_rule = self._oracle["alternative_quotes"]

        minimum_quotes = int(quote_rule["minimum_quotes"])
        finance_required = amount > Decimal(str(finance_rule["threshold_try"]))
        quote_missing = (
            amount > Decimal(str(quote_rule["threshold_try"])) and received_quotes < minimum_quotes
        )
        certificate_valid = (
            certificate_expiry >= request_date
            if self._oracle["supplier_certificate"]["must_be_valid_on_request_date"]
            else True
        )
        supplier_rejected = (
            bool(self._oracle.get("supplier_status", {}).get("must_be_active", False))
            and supplier_status != "active"
        )
        blocked = finance_required or quote_missing or not certificate_valid
        if supplier_rejected:
            decision_status = "REJECTED"
        elif blocked:
            decision_status = "CONDITIONAL_REVIEW"
        else:
            decision_status = "APPROVED"
        return {
            "decision_status": decision_status,
            "finance_approval_required": finance_required,
            "alternative_quote_missing": quote_missing,
            "certificate_status": "VALID" if certificate_valid else "EXPIRED",
        }

    def _security_case(self, case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        data = case["input"]
        if "text" in data:
            actual = {"injection_detected": contains_prompt_injection(data["text"])}
        else:
            actual = {"authorized": _is_authorized(data["role"], data["action"])}
        return dict(case["expected"]), actual

    def _retrieval_case(self, case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        data = case["input"]
        role = str(data["role"])
        repository = self._policy_documents()
        result = PolicyQaService(repository).ask(
            str(data["question"]),
            on_date=date.fromisoformat(data["on_date"]),
            role=role,
        )
        sections = result["sections"]
        statuses = {
            document.document_id: document.status
            for document in repository.searchable_documents(role)
        }
        actual = {
            "top_document_id": sections[0]["document_id"] if sections else None,
            "superseded_retrieved": any(
                statuses.get(section["document_id"]) != "CURRENT" for section in sections
            ),
            "untrusted_retrieved": any(
                section["document_id"] == _UNTRUSTED_DOCUMENT_ID for section in sections
            ),
        }
        return dict(case["expected"]), actual

    def _policy_documents(self) -> PolicyRepository:
        if self._repository is None:
            self._repository = PolicyRepository(self._documents_path)
        return self._repository

    def _idempotency_case(self, case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        key = str(case["input"]["key"])
        expected = self._idempotency_oracle(key)
        result = self._tickets.create_ticket({"request_id": key}, key)
        actual = {"ticket_count": self._tickets.ticket_count(), "status": result.status}
        return expected, actual

    def _idempotency_oracle(self, key: str) -> dict[str, Any]:
        duplicate_allowed = bool(self._oracle["idempotency"]["duplicate_ticket_allowed"])
        replay = key in self._seen_keys and not duplicate_allowed
        if not replay:
            self._seen_keys.add(key)
            self._expected_ticket_count += 1
        return {
            "ticket_count": self._expected_ticket_count,
            "status": "ALREADY_PROCESSED" if replay else "OPEN",
        }


def _is_authorized(role: str, action: str) -> bool:
    try:
        authorize(role, action)
    except AuthorizationError:
        return False
    return True
