# Evaluation Cases

These files define future machine-readable regression cases. They are not measured customer results.

## Rules

- Runtime application code reads `data/policy_rules.yaml`.
- The evaluation runner reads `evals/policy_oracle.yaml`.
- Security cases are not parameterized by the oracle file, so their frozen `expected` block is the oracle for those cases.
- Cases are frozen before prompt or retrieval tuning.
- Failed cases remain in reports.
- README metrics may only be populated from generated evaluation output.

## Running

`make evals` runs `python scripts/run_evals.py`, which writes the untracked report `reports/evaluation.json` and exits non-zero when a case fails.
