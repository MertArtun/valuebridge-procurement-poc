# Evaluation Cases

These files define machine-readable regression cases. They are not measured customer results.

## Families

| File | Cases | What a case asserts |
|---|---:|---|
| `policy_decision_cases.jsonl` | 6 | Decision status, applied rules and citations for a purchase request |
| `security_cases.jsonl` | 4 | Authorization, quarantine and disclosure behavior |
| `idempotency_cases.jsonl` | 3 | Replay and conflict behavior for a repeated action |
| `rag_cases.jsonl` | 2 | Governed retrieval: what may and may not become a candidate |

Fifteen cases in total, all runnable without provider credentials.

## Model quality benchmarks

`benchmarks/` holds the two datasets that score a live model rather than the deterministic core. They sit in a subdirectory so the `evals/*.jsonl` glob behind `scripts/run_evals.py` and `scripts/verify.py` never picks them up.

| File | Cases | What a case scores |
|---|---:|---|
| `benchmarks/intake_benchmark.jsonl` | 15 | Field-by-field agreement between a model's intake draft and the expected `PurchaseRequestDraft` |
| `benchmarks/qa_benchmark.jsonl` | 15 | Top-ranked policy section, answer groundedness and abstention on out-of-corpus questions |

`scripts/run_llm_benchmark.py` runs them and needs `VALUEBRIDGE_LLM_API_KEY`; see `docs/08_EVALUATION_PLAN.md`.

## Rules

- Runtime application code reads `data/policy_rules.yaml`.
- The evaluation runner reads `evals/policy_oracle.yaml`.
- Security, idempotency and RAG cases are not parameterized by the oracle file, so their frozen `expected` block is the oracle for those cases.
- Cases are frozen before prompt or retrieval tuning.
- Failed cases remain in reports.
- README metrics may only be populated from generated evaluation output.

## Governed retrieval cases

`RAG-001` and `RAG-002` check the retrieval boundary rather than answer wording, because that boundary is what has to hold whether or not a model is configured. `RAG-001` asks the finance-threshold question and requires the current procurement policy to rank first with no superseded section retrieved. `RAG-002` asks an injected question and requires no untrusted supplier content to appear at any rank. Both are decided by candidate scoping and lexical ranking, which is exactly the state a provider outage leaves behind.

## Running

`make evals` runs `python scripts/run_evals.py`, which writes the untracked report `reports/evaluation.json` and exits non-zero when a case fails.
