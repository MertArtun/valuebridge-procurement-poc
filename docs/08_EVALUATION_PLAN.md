# Evaluation and Test Strategy

## Principle

System claims must come from executable tests or a controlled pilot, not manually typed success percentages.

## Test layers

### Domain tests

- Decimal arithmetic and request-date history boundary
- Effective policy selection
- Policy/runtime threshold alignment
- Finance, quote and certificate decisions
- Role authorization and injection detection
- Retry-delay parsing and bounds

### Integration and concurrency tests

- Approval persistence, rejection and expiry
- Concurrent approve/reject and concurrent expiry
- Same-key/same-payload idempotent replay
- Same-key/different-payload conflict
- Concurrent ticket creation with same and different keys
- Structured domain failure and audit evidence
- Safe browser rendering contract

### Frozen evaluation cases

`app/evaluation.py` executes JSONL cases from `evals/` through `scripts/run_evals.py` and writes `reports/evaluation.json`. Expected policy behavior comes from `evals/policy_oracle.yaml`, not application return values. A frozen case that contradicts the oracle fails as dataset drift.

## Objective system metrics

- Policy decision matches oracle
- Effective policy selected for request date
- Citation section matches applied rule
- Unauthorized access successes
- Write without approval count
- Duplicate ticket count under sequential and concurrent replay
- Idempotency payload conflicts
- Injection bypass count
- Tool payload schema conformance

## Workflow impact

Cycle time, manual touch count, approval turnaround, adoption, repeat use and estimated time saved remain `NOT_MEASURED`. Synthetic data is not used to claim customer impact.

## Required verification

```bash
ruff check .
node --check app/static/app.js
pytest -q
python scripts/verify.py
python scripts/run_evals.py
docker compose up -d --build
bash scripts/demo.sh
docker compose down -v
```

GitHub Actions runs both a quality/archive path and a Docker Compose end-to-end smoke path.
