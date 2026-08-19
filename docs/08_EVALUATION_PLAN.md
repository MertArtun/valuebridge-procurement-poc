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

### LLM quality benchmark

The frozen families prove the deterministic core; they say nothing about how well a given model reads Turkish free text or answers from a retrieved section. `scripts/run_llm_benchmark.py` measures exactly that, against a live provider, for one or more models at a time.

| Suite | File | Cases | What a case scores |
|---|---|---:|---|
| Intake extraction | `evals/benchmarks/intake_benchmark.jsonl` | 15 | Field-by-field agreement between the model's draft and the expected `PurchaseRequestDraft` |
| Policy answering | `evals/benchmarks/qa_benchmark.jsonl` | 15 | Which section ranks first, whether the answer carries the facts it cites, and whether the model abstains when it should |

Intake cases cover complete requests, partial ones where two or more fields must stay `null`, Turkish number and date spellings (`320 bin`, `1,5 milyon`, `3 Eylül 2026`), category mapping onto the prompt's vocabulary, supplier names taken from `data/suppliers.csv`, two prompt-injection attempts whose expected draft is the clean one, and one wholly unrelated text whose expected draft is all `null`. Q&A cases are derived from the section bodies of `data/procurement_policy_2026_current.md` and `data/supplier_compliance_policy.md`, including an uppercase-Turkish phrasing that exercises the `İ` tokenizer fix, plus three questions the corpus cannot answer.

This benchmark is deliberately outside CI. It needs `VALUEBRIDGE_LLM_API_KEY`, it calls a paid provider, and its numbers move when the provider changes a model behind a stable id — none of which belongs in a gate that must stay keyless, offline and reproducible. `reports/llm_benchmark.json` is untracked for the same reason: it is a point-in-time measurement, not a frozen result. The scoring functions themselves are keyless and covered by `tests/test_llm_benchmark.py`, so the measurement code is under test even though the measurement is not.

```bash
export VALUEBRIDGE_LLM_API_KEY=...
python scripts/run_llm_benchmark.py \
  --model anthropic/claude-sonnet-5 \
  --model google/gemini-2.5-flash-lite \
  --suite all
```

`--model` repeats to compare models and falls back to `VALUEBRIDGE_LLM_MODEL`; `--suite` selects `intake`, `qa` or `all`; `--output` overrides the report path. Without a key the run exits 1 before any request is made. Metric definitions:

- **mean_field_accuracy** — mean over cases of correct fields divided by seven. A field is correct only on exact match, and an expected `null` requires an emitted `null`, so inventing a plausible value costs the same as missing a real one.
- **perfect_cases** — cases where all seven fields matched.
- **parse_failures** — cases that produced no valid draft, whether the completion was unparseable or the provider call failed. Such a case scores zero; `per_case[].error` names the cause.
- **top1_accuracy** — share of cases whose first ranked section is the expected one. An abstain case counts as a hit when the system abstains.
- **groundedness** — share of the case's `must_contain` strings present in the answer, compared casefolded. It checks that a cited number or section identifier actually appears, not that the prose is good.
- **abstain_accuracy** — share of cases where observed abstention matched the expectation. Both directions count: answering an out-of-corpus question and refusing an answerable one are equally wrong. A case counts as abstaining when the answer carries the sentence `Bu bilgi politika korpusunda yok.`, or when governed retrieval returned no section at all and the system therefore refused one layer earlier.
- **p50_ms / p95_ms** — nearest-rank percentiles of per-call latency within a suite.

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

The suite currently reports 202 passing tests, `scripts/verify.py` 9 project invariants and `scripts/run_evals.py` 15 passing cases. Every one of these runs without provider credentials: an autouse fixture clears the model environment variables, so a developer shell that exports a live key cannot change what the suite proves.

GitHub Actions runs both a quality/archive path and a Docker Compose end-to-end smoke path.
