# Evaluation and Test Strategy

## Principle

System claims must come from executable tests or a controlled pilot, not from manually typed success percentages.

## Test layers

### Unit tests

- Decimal analysis
- Policy rule evaluation
- Role authorization
- Injection detection
- Policy version selection

### Integration tests

- Approval persistence
- MockDesk idempotency
- ValueBridge API hero flow
- Future HTTP retry and action-preview contract

### Evaluation cases

`evals/` contains frozen machine-readable cases. `app/evaluation.py` executes them through `scripts/run_evals.py` (`make evals`) and writes `reports/evaluation.json`. Cases cover policy decisions, authorization, prompt injection, stale policy and idempotency.

## Oracle separation

The application reads `data/policy_rules.yaml`. Evaluation tooling reads `evals/policy_oracle.yaml`. The runner calculates expected behavior independently from application return values. A frozen case whose `expected` block contradicts the oracle fails as dataset drift.

## Discovery evaluation

Do not headline precision/recall from a transcript authored by the same developer. Prefer:

- Unsupported extraction count
- Evidence-anchor coverage
- Inference correctly marked as inference
- Human-accepted requirement count
- Human-corrected requirement count
- Requirement-to-test traceability coverage

The starter does not automate discovery extraction, so these remain documentation practices rather than product metrics.

## Objective system metrics

- Policy decision matches oracle
- Current policy selected
- Citation section matches rule
- Unauthorized document access count
- Write without approval count
- Duplicate ticket count
- Injection bypass count
- Tool payload conforms to schema

## Workflow-impact metrics

These are `NOT_MEASURED` in the starter:

- End-to-end cycle time
- Manual touch count
- Approval turnaround
- Fallback rate
- Human correction rate
- Adoption and repeat usage
- Estimated time saved

## Dataset discipline

- Freeze evaluation cases before tuning prompts or retrieval settings.
- Keep development examples separate from final evaluation cases.
- Preserve failed cases in reports.
- Generate README results only from the runner output.
- Never delete a failed case solely to improve a score.

## Required commands

```bash
pytest -q
python scripts/verify.py
python scripts/run_evals.py
ruff check .
```

Docker verification must be run separately on a Docker-capable machine.
