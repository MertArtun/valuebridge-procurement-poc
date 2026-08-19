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

`app/evaluation.py` executes JSONL cases from `evals/` through `scripts/run_evals.py` and writes `reports/evaluation.json`. Fifteen cases run today across four families:

| Family | File | Cases | Oracle |
|---|---|---:|---|
| Policy decision | `policy_decision_cases.jsonl` | 6 | `evals/policy_oracle.yaml` |
| Security | `security_cases.jsonl` | 4 | The frozen `expected` block |
| Idempotency | `idempotency_cases.jsonl` | 3 | The frozen `expected` block |
| Governed retrieval | `rag_cases.jsonl` | 2 | The frozen `expected` block |

Expected policy behavior comes from `evals/policy_oracle.yaml`, not application return values. A frozen case that contradicts the oracle fails as dataset drift. The security, idempotency and retrieval families are not parameterized by the oracle file, so their frozen `expected` block is the oracle for those cases.

The retrieval cases assert governance, not answer quality, because governance is the part that must hold with or without a model:

- `RAG-001` — the finance-threshold question ranks the current procurement policy first and retrieves no superseded section.
- `RAG-002` — an injected question retrieves no untrusted supplier content.

Both run keyless: they exercise candidate scoping and lexical ranking, which is what a provider outage would leave in place.

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
- Superseded or untrusted sections reaching a retrieval result
- Decision fields identical with the model layer on and off

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

The suite currently reports 171 passing tests, `scripts/verify.py` 9 project invariants and `scripts/run_evals.py` 15 passing cases. Every one of these runs without provider credentials: an autouse fixture clears the model environment variables, so a developer shell that exports a live key cannot change what the suite proves.

GitHub Actions runs both a quality/archive path and a Docker Compose end-to-end smoke path.
