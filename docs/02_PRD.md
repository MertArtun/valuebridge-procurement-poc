# Product Requirements Document — ValueBridge

## Product vision

ValueBridge demonstrates how a Solution Engineer converts a fragmented procurement exception process into a controlled, explainable and measurable AI-assisted workflow without delegating financial authority or enterprise write permissions to an LLM.

## Problem

The synthetic as-is process requires employees to search policies manually, calculate comparisons in spreadsheets, inspect supplier documents, request approval through email and re-enter data into a ticketing system. The result is exposed to stale policy use, arithmetic errors, missing evidence, ambiguous approval, duplicate records and weak auditability.

## Goals

- Select the policy effective on the request date.
- Analyze the hero purchase request with reproducible arithmetic.
- Separate deterministic decisions from optional language-model narration.
- Refuse a request from a non-active supplier instead of routing it to approval.
- Require an explicit finance approval for every blocking decision.
- Answer policy questions only from sections the asker is allowed to read on that date.
- Report pilot metrics from the audit trail rather than a separate counter.
- Preview the exact outbound action before execution.
- Demonstrate an HTTP integration through MockDesk.
- Prevent duplicate writes under sequential and concurrent retries.
- Preserve evidence suitable for troubleshooting and audit.
- Run without external credentials.

## Non-goals

- Autonomous purchasing or payment
- General-purpose procurement SaaS
- Real Jira, ERP or SkyStudio integration
- Production SSO, multi-tenancy or cloud infrastructure
- Multi-agent framework or workflow-canvas builder
- Business-impact claims based on synthetic data

## Personas

- **Procurement Specialist:** analyzes requests and executes an approved action; cannot approve finance action.
- **Finance Approver:** approves or rejects a required finance action.
- **Solution Engineer:** configures the scenario, validates integrations and inspects audit evidence.
- **Auditor:** reads the event trail; cannot create, approve or execute requests.

## Hero workflow

```text
Free-Text Intake (optional, human-reviewed)
→ Purchase Request
→ Role Check
→ Effective Policy Retrieval
→ Purchase-History Analysis
→ Supplier Compliance Check
→ Deterministic Policy Evaluation
→ Evidence-Backed Explanation
→ Action Preview
→ Finance Approval
→ Idempotency Check
→ MockDesk Ticket
→ Audit Trail
```

## Core functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| FR-001 | Validate the request through typed API and UI contracts. | API/schema tests |
| FR-002 | Authorize analysis, approval, execution and audit server-side. | Authorization tests |
| FR-003 | Select the policy effective on the request date. | Temporal policy tests |
| FR-004 | Exclude policies and purchases outside the request-date boundary. | Temporal analysis tests |
| FR-005 | Calculate median and variance with `Decimal`. | Analysis tests |
| FR-006 | Evaluate finance, quote and certificate rules deterministically. | Policy tests |
| FR-007 | Cite only policy sections mapped to applied rules. | Citation tests |
| FR-008 | Create one `finance_approver` approval for every `CONDITIONAL_REVIEW` decision, reused on an identical re-analysis and superseded after a correction. | Low/high-risk API and request-revision tests |
| FR-009 | Block execution until the approval is `APPROVED`. | Approval tests |
| FR-010 | Make terminal approval transitions atomic. | Concurrency tests |
| FR-011 | Show the server-generated outbound action before execution. | Action-preview tests |
| FR-012 | Bind each idempotency key to a canonical payload hash. | Idempotency tests |
| FR-013 | Replay same-key/same-payload and reject changed payloads. | Conflict tests |
| FR-014 | Bound retry/backoff and preserve the key on every attempt. | Integration tests |
| FR-015 | Quarantine untrusted supplier instructions outside policy context. | Injection tests |
| FR-016 | Persist success and failure events with trace IDs. | Audit tests |
| FR-017 | Render API-controlled values without executable markup. | UI security tests |
| FR-018 | Export frozen evaluation results as machine-readable JSON. | Evaluation runner tests |
| FR-019 | Reject a request from a non-active supplier and open no approval. | `test_rejected_decision.py` |
| FR-020 | Derive pilot metrics from stored audit events only. | `test_metrics.py` |
| FR-021 | Draft a free-text intake into a reviewable request without starting the analysis, flagging injection attempts as data. | `test_intake.py` |
| FR-022 | Filter policy candidates by effective date, role and trust before any relevance score is computed. | `test_policy_qa.py`, RAG evaluation cases |
| FR-023 | Keep every model-produced field display-only and absent when the provider is unset or failing. | `test_llm_narrator.py`, `test_llm_env_isolation.py` |

## Non-functional requirements

| Category | Target |
|---|---|
| Duplicate writes, same key/same payload | 0 |
| Same key/different payload | `409 IDEMPOTENCY_CONFLICT` |
| Write actions without approval | 0 |
| Unauthorized policy-content disclosure | 0 successful cases |
| Hero median | Exactly 184,500 TRY |
| Hero exact variance | Exactly 19.2412% |
| External credentials for core flow | None |
| Real customer data | None |
| Unmeasured business results | Never presented as achieved |

## Decision boundary

Deterministic components own arithmetic, dates, thresholds, authorization, approval state, idempotency and tool permission. The model layer is display-only: it drafts an intake a human must review, narrates a decision that is already locked and answers a policy question from sections retrieval already governed. It cannot change a rule result, an approval state, a tool parameter or which documents are retrievable.

The layer is optional. Without `VALUEBRIDGE_LLM_API_KEY` the intake endpoint returns `503 LLM_DISABLED`, `llm_narrative` and the policy answer are `null`, and every other response is byte-identical. Model provider and model id are configuration, because no model owns a decision.

## Implemented API

```text
GET  /health
POST /api/v1/requests/intake
POST /api/v1/requests/analyze
POST /api/v1/policies/ask
GET  /api/v1/approvals/{approval_id}/action-preview
POST /api/v1/approvals/{approval_id}/approve
POST /api/v1/approvals/{approval_id}/reject
POST /api/v1/tool-actions/{approval_id}/execute
GET  /api/v1/audit/events
GET  /api/v1/metrics/summary
```

The frozen evaluation suite is an offline CLI/CI job through `scripts/run_evals.py`; no public evaluation endpoint is exposed.

## Error contract

- `403`: role not authorized
- `404`: supplier, request or approval not found
- `409`: approval conflict or idempotency conflict
- `422`: schema validation or insufficient domain evidence
- `502`: normalized downstream integration failure, including an unreachable model provider (`LLM_UNAVAILABLE`) or an unusable intake draft (`INTAKE_EXTRACTION_FAILED`)
- `503`: the optional model layer is not configured (`LLM_DISABLED`)

Structured domain errors contain a stable code, human-readable message, trace ID where available and `retryable` flag.

## Release gates

- **Core gate:** tests and invariant checks pass without model credentials.
- **Application candidate:** security, temporal, concurrency, evaluation and Docker smoke paths exist.
- **Manual publication gate:** CI is green, repository is public and the 90-second demo is linked.
