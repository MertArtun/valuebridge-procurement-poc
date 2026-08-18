from __future__ import annotations

import json
from pathlib import Path

from app.evaluation import run_evaluation, write_report

TEMPORARY_ORACLE = """\
version: "oracle-test"
finance_approval:
  threshold_try: 500000
  comparison: greater_than
alternative_quotes:
  threshold_try: 100000
  minimum_quotes: 2
supplier_certificate:
  must_be_valid_on_request_date: true
"""

PROJECT_RULES = Path("data/policy_rules.yaml")


def _temporary_case(case_id: str, amount_try: str, finance_approval_required: bool) -> dict:
    return {
        "case_id": case_id,
        "description": f"Finance approval expectation for {amount_try} TRY",
        "input": {
            "amount_try": amount_try,
            "received_quotes": 2,
            "request_date": "2026-08-18",
            "certificate_expiry": "2027-01-01",
        },
        "expected": {"finance_approval_required": finance_approval_required},
        "severity": "HIGH",
    }


def _temporary_suite(tmp_path: Path) -> tuple[list[Path], Path]:
    cases_path = tmp_path / "policy_decision_cases.jsonl"
    cases_path.write_text(
        "".join(
            json.dumps(case, ensure_ascii=False) + "\n"
            for case in (
                _temporary_case("POL-T1", "600000", True),
                _temporary_case("POL-T2", "220000", False),
            )
        ),
        encoding="utf-8",
    )
    oracle_path = tmp_path / "policy_oracle.yaml"
    oracle_path.write_text(TEMPORARY_ORACLE, encoding="utf-8")
    return [cases_path], oracle_path


def test_report_has_the_required_shape_and_counts(tmp_path: Path) -> None:
    case_paths, oracle_path = _temporary_suite(tmp_path)

    report = run_evaluation(case_paths, oracle_path=oracle_path, policy_rules_path=PROJECT_RULES)

    assert list(report) == ["run_id", "generated_at", "counts", "cases"]
    assert report["run_id"]
    assert report["generated_at"]
    assert report["counts"] == {"passed": 1, "failed": 1}
    assert [case["case_id"] for case in report["cases"]] == ["POL-T1", "POL-T2"]


def test_failed_case_is_preserved_with_reason_and_actual_output(tmp_path: Path) -> None:
    case_paths, oracle_path = _temporary_suite(tmp_path)

    report = run_evaluation(case_paths, oracle_path=oracle_path, policy_rules_path=PROJECT_RULES)

    failed = [case for case in report["cases"] if case["status"] == "FAILED"]
    assert len(failed) == 1
    assert failed[0]["case_id"] == "POL-T2"
    assert failed[0]["expected"] == {"finance_approval_required": False}
    assert failed[0]["actual"] == {"finance_approval_required": True}
    assert "finance_approval_required" in failed[0]["reason"]


def test_write_report_stores_the_report_as_json(tmp_path: Path) -> None:
    case_paths, oracle_path = _temporary_suite(tmp_path)
    report = run_evaluation(case_paths, oracle_path=oracle_path, policy_rules_path=PROJECT_RULES)
    output_path = tmp_path / "reports" / "evaluation.json"

    write_report(report, output_path)

    assert json.loads(output_path.read_text(encoding="utf-8")) == report


def test_project_evaluation_cases_pass() -> None:
    report = run_evaluation(
        sorted(Path("evals").glob("*.jsonl")),
        oracle_path=Path("evals/policy_oracle.yaml"),
        policy_rules_path=PROJECT_RULES,
    )

    assert report["counts"]["failed"] == 0
    assert report["counts"]["passed"] == len(report["cases"])
    assert report["counts"]["passed"] > 0
