# Solution Architecture

## Goals

- Keep business decisions reproducible.
- Make human authorization explicit.
- Make duplicate prevention demonstrable.
- Keep the demo credential-free and small enough for an application sprint.
- Preserve replaceable production-oriented boundaries.

## Containers

### ValueBridge web/API

FastAPI serves the HTML demo and JSON endpoints. It orchestrates effective-policy retrieval, analysis, deterministic policy evaluation, approval state and audit.

### SQLite

Local persistence for approvals, case snapshots and audit events. Immediate transactions and compare-and-set conditions protect terminal state transitions.

### MockDesk

Independent FastAPI service representing an enterprise ticketing integration. It owns payload-bound, atomic idempotency.

### Optional model provider

Not part of the core runtime. `app/llm.py` defines a `ChatClient` protocol and `app/policy_qa.py` an `EmbeddingClient` protocol; the shipped implementations speak the OpenAI-compatible chat-completions and embeddings contracts through OpenRouter, so the provider and model id are environment configuration rather than code. Prompts live in `app/prompts/*.md`.

Both clients are constructed only when `VALUEBRIDGE_LLM_API_KEY` is set, and every call site degrades instead of failing: a missing chat client makes intake return `503 LLM_DISABLED`, a failing one leaves `llm_narrative` and the policy answer `null`, and a missing, malformed or unreachable embedding layer drops hybrid retrieval back to `lexical`. The provider narrates, drafts and answers; it never evaluates a rule, authorizes an actor or executes a tool.

## Module boundaries

| Module | Responsibility | Must not do |
|---|---|---|
| `analysis.py` | Median, variance and lead-time calculations | Read approval state |
| `retrieval.py` | Trust/role/effective-period selection and section parsing | Evaluate business rules |
| `policy_engine.py` | Deterministic rule evaluation | Generate tool calls |
| `security.py` | Role policy and injection detection | Persist domain state |
| `store.py` | Approval, case and audit persistence | Interpret policy text |
| `service.py` | Orchestrate the use case | Hide decision inputs |
| `llm.py` | Provider-agnostic chat client and prompt loading | Reach a decision or a store |
| `policy_qa.py` | Governed candidate scoping, BM25/hybrid ranking and grounded answering | Widen the candidate set by score |
| `metrics.py` | Fold audit events into pilot metrics | Read domain tables directly |
| `mockdesk_client.py` | Integration, retry and error boundary | Approve actions |
| `mockdesk/store.py` | Atomic idempotent ticket persistence | Re-evaluate policy |

## Request flow

1. API validates `PurchaseRequest`.
2. Server authorizes the actor.
3. Supplier record and request-bounded purchase history are loaded.
4. Repository selects policies effective on the request date.
5. Analysis calculates values with `Decimal`.
6. Policy engine creates `PolicyDecision`.
7. Service maps applied rule IDs to citations.
8. Store creates one pending `finance_approver` approval for every blocking decision; a re-analysis with the same request fingerprint reuses it, a corrected one supersedes it. A `REJECTED` decision opens no approval at all.
9. The narrator, if configured, describes the already persisted decision; its output is attached to the response and to nothing else.
10. Finance approves or rejects; compare-and-set permits one terminal transition.
11. Procurement executes only an approved action.
12. MockDesk atomically creates or replays the payload-bound ticket.
13. Audit events reconstruct success and failure paths.

## Policy question flow

1. API validates the question and the date it is asked about.
2. Server authorizes the actor for `ask_policy_question`.
3. `policy_qa.py` builds the candidate set from documents the role may read whose status is `CURRENT` and whose effective window covers the asked date. Superseded policy and untrusted supplier attachments are excluded here, before any score exists, so no ranking signal can promote them back in.
4. BM25 scores the surviving sections; Turkish text is lowercased before tokenization so a dotted capital `İ` does not split a word.
5. When an embedding client and `data/policy_embeddings.json` are both present, cosine similarity is blended with the normalized lexical score and the response reports `hybrid`; otherwise, and on any embedding failure, it reports `lexical`.
6. The optional answer is generated strictly from the returned sections and cites their section numbers; the sections stand alone when no answer is produced.
7. The question, its retrieval mode and any matched injection rule are audited.

## Metrics

`metrics.py` folds the stored audit events into the pilot summary served by `GET /api/v1/metrics/summary`: decision mix, approval outcomes, tickets created, duplicates prevented, quarantined attachments, denied or blocked actions and median cycle time. It reads no domain table, so a metric can never claim something the audit trail cannot reconstruct.

## Trust boundaries

Browser input, supplier attachments, optional model output and MockDesk responses are untrusted. Policy content becomes trusted only after manifest trust, role and effective-period filters. Approval state is authoritative only in the application store.

## Failure behavior

- Schema validation: FastAPI `422`; no approval created.
- Domain evidence failure: structured `404/422` with trace ID and audit event.
- Authorization: `403` with `AUTHORIZATION_DENIED` for analysis, `APPROVAL_DENIED` for a decision by a role the approval does not name and `TOOL_EXECUTION_DENIED` for execution.
- Execution before approval or against a terminal approval: `409` with `TOOL_EXECUTION_BLOCKED` recording the current approval status.
- Decision on a terminal approval: `409` with `APPROVAL_TRANSITION_FAILED` recording the target and current status.
- Unknown approval identifier: `404` without an audit event.
- Same idempotency key with changed payload: `409 IDEMPOTENCY_CONFLICT`.
- Transient 429/503/504 or transport error: bounded retry with same key.
- Persistent downstream failure: normalized `502` and audit event.
- Intake without a configured provider: `503 LLM_DISABLED` and an `INTAKE_FAILED` audit event.
- Model provider error during intake: normalized `502` carrying only the failure class or status code, never the provider body.
- Model provider error during narration or answering: the field stays `null`, the decision and the retrieved sections are unchanged, and narration records `NARRATION_SKIPPED`.

## Deployment

Native mode runs two Uvicorn processes. Docker Compose uses the same non-root image with separate entry commands and a named runtime volume. No cloud service is required.

## Replacement path

| PoC component | Production-oriented replacement |
|---|---|
| SQLite | Managed PostgreSQL |
| Demo headers | OIDC/SSO claims |
| File manifests | Governed knowledge repository |
| File-backed embedding index next to BM25 | Governed vector store with ACL-aware reranking |
| MockDesk | Jira/ServiceNow/ERP adapter |
| Optional narration through a hosted provider | Reviewed and evaluated provider or a SkyStudio assistant |
| Local audit | Central immutable audit infrastructure |
