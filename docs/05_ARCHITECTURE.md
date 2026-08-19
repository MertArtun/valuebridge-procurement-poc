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

Not part of the core runtime. A future provider may narrate a precomputed decision but cannot own rule evaluation, authorization or tool execution.

## Module boundaries

| Module | Responsibility | Must not do |
|---|---|---|
| `analysis.py` | Median, variance and lead-time calculations | Read approval state |
| `retrieval.py` | Trust/role/effective-period selection and section parsing | Evaluate business rules |
| `policy_engine.py` | Deterministic rule evaluation | Generate tool calls |
| `security.py` | Role policy and injection detection | Persist domain state |
| `store.py` | Approval, case and audit persistence | Interpret policy text |
| `service.py` | Orchestrate the use case | Hide decision inputs |
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
8. Store creates one pending `finance_approver` approval for every blocking decision; a re-analysis with the same request fingerprint reuses it, a corrected one supersedes it.
9. Finance approves or rejects; compare-and-set permits one terminal transition.
10. Procurement executes only an approved action.
11. MockDesk atomically creates or replays the payload-bound ticket.
12. Audit events reconstruct success and failure paths.

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

## Deployment

Native mode runs two Uvicorn processes. Docker Compose uses the same non-root image with separate entry commands and a named runtime volume. No cloud service is required.

## Replacement path

| PoC component | Production-oriented replacement |
|---|---|
| SQLite | Managed PostgreSQL |
| Demo headers | OIDC/SSO claims |
| File manifests | Governed knowledge repository |
| Lexical section retrieval | ACL-aware hybrid retrieval/reranking |
| MockDesk | Jira/ServiceNow/ERP adapter |
| Template narrator | Validated model provider or SkyStudio assistant |
| Local audit | Central immutable audit infrastructure |
