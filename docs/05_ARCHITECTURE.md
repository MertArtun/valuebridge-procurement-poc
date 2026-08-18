# Solution Architecture

## Architectural goals

- Keep the business decision reproducible.
- Make human authorization explicit.
- Make duplicate prevention demonstrable.
- Keep the local demo credential-free.
- Preserve boundaries that a production implementation could replace.
- Remain small enough for an application sprint.

## Containers

### ValueBridge web/API

FastAPI application serving the HTML demo and JSON endpoints. It orchestrates retrieval, analysis, policy evaluation, approval state and audit.

### SQLite

Local persistence for approvals, case snapshots and audit events. SQLite is intentionally used for a portable PoC; the repository boundary allows replacement.

### MockDesk

Independent FastAPI service representing an enterprise ticketing integration. It owns ticket idempotency.

### Optional model provider

Not part of the core runtime. A future provider may narrate a precomputed decision but must never own rule evaluation or authorization.

## Module boundaries

| Module | Responsibility | Must not do |
|---|---|---|
| `analysis.py` | Median, variance, lead-time calculation | Read approvals or call models |
| `retrieval.py` | Accessible, effective document selection and section parsing | Evaluate business rules |
| `policy_engine.py` | Deterministic rule evaluation | Generate tool calls |
| `security.py` | Role policy and injection detection | Persist domain state |
| `store.py` | Approval, case and audit persistence | Interpret policy text |
| `service.py` | Orchestrate the use case | Hide decision inputs |
| `mockdesk_client.py` | Integration boundary | Approve the action |
| `mockdesk/store.py` | Ticket idempotency | Re-evaluate procurement policy |

## Request flow

1. API validates `PurchaseRequest`.
2. Role policy authorizes analysis.
3. Supplier record and history are loaded.
4. `PolicyRepository` selects the effective current policy.
5. `analyze_purchase_history` calculates values with `Decimal`.
6. `PolicyEngine` creates `PolicyDecision`.
7. Store creates pending approval and case snapshot.
8. API returns analysis, reasons, citations and approval ID.
9. Finance role approves.
10. Procurement role executes the approved action.
11. MockDesk creates or returns the idempotent ticket.
12. Audit events reconstruct the flow.

## Trust boundaries

- Browser input is untrusted.
- Supplier attachments are untrusted document content.
- Policy documents are trusted only when manifest metadata marks them trusted and accessible.
- Model output, when added, is untrusted until schema validation.
- MockDesk is an external system boundary even though it is local in the PoC.
- Approval state is authoritative only in the application store.

## Failure handling

### Validation failure

Return `400` or FastAPI validation response; do not create approval.

### Authorization failure

Return `403`, create no write state, and later emit security audit evidence.

### Missing evidence

Return `INSUFFICIENT_EVIDENCE`; do not propose write execution.

### Approval missing

Return `409 APPROVAL_REQUIRED`.

### Duplicate execution

Return the original ticket with `ALREADY_PROCESSED`.

### Transient integration failure

Planned behavior: bounded retry, exponential backoff, same idempotency key, auditable final failure.

## Deployment

Local native mode runs two Uvicorn processes. Docker Compose uses the same image with different entry commands. No cloud service is required.

## Replacement path

| PoC component | Production-oriented replacement |
|---|---|
| SQLite | Managed PostgreSQL |
| Demo headers | OIDC/SSO claims |
| File manifests | Governed knowledge repository |
| Lexical section retrieval | ACL-aware hybrid retrieval and reranking |
| MockDesk | Jira/ServiceNow/ERP adapter |
| Template narrator | Validated model provider or SkyStudio assistant |
| Local logs | Central observability and immutable audit storage |
