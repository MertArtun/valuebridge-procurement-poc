# Evaluation Cases

These files define future machine-readable regression cases. They are not measured customer results.

## Rules

- Runtime application code reads `data/policy_rules.yaml`.
- The evaluation runner reads `evals/policy_oracle.yaml`.
- Cases are frozen before prompt or retrieval tuning.
- Failed cases remain in reports.
- README metrics may only be populated from generated evaluation output.
