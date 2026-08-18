from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation import run_evaluation, write_report  # noqa: E402

REPORT_PATH = ROOT / "reports/evaluation.json"


def main() -> int:
    report = run_evaluation(
        sorted((ROOT / "evals").glob("*.jsonl")),
        oracle_path=ROOT / "evals/policy_oracle.yaml",
        policy_rules_path=ROOT / "data/policy_rules.yaml",
    )
    write_report(report, REPORT_PATH)

    for case in report["cases"]:
        if case["status"] == "FAILED":
            print(f"FAIL: {case['case_id']} ({case['severity']}) {case['reason']}")
    counts = report["counts"]
    print(f"PASS: {counts['passed']} evaluation cases, FAILED: {counts['failed']}")
    print(f"Report: {REPORT_PATH.relative_to(ROOT)}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
