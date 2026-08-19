# Scope and Definition of Done

## Locked core scope

- One synthetic procurement exception scenario
- Effective-date procurement and supplier-compliance policies
- Purchase-history analysis bounded by request date
- Deterministic policy engine
- Conditional human finance approval
- MockDesk HTTP integration
- Atomic, payload-aware idempotency
- Atomic approval state transitions
- Role controls
- Audit trail and structured domain failures
- Indirect prompt-injection quarantine
- Safe browser rendering and security headers
- Local runtime and Docker Compose

## Explicit non-goals

- General procurement SaaS
- Real customer data, purchasing or payment
- Real Jira, ERP, Slack or live SkyStudio dependency
- Multi-agent framework or workflow builder
- Keycloak, Kubernetes, Terraform, Grafana or cloud deployment
- Advanced vector-RAG infrastructure
- Business-impact claims from synthetic data

## Core done

- [x] Hero amount, median and variance are deterministic.
- [x] Policy selection is bounded to the current policy set; out-of-window request dates fail with an explicit error and the superseded policy is never used.
- [x] Purchase history excludes records after the request date.
- [x] Finance, quote and certificate rules are deterministic.
- [x] Policy citations map to rules actually applied.
- [x] A low-risk request creates no unnecessary finance approval.
- [x] Tool execution is blocked before approval.
- [x] Only the finance role may approve or reject.
- [x] Approval, rejection and expiry transitions are atomic.
- [x] Same idempotency key and payload create no second ticket.
- [x] Same key with changed payload returns `IDEMPOTENCY_CONFLICT`.
- [x] Retry/backoff is bounded and preserves the key.
- [x] Untrusted supplier instructions are quarantined and excluded.
- [x] API-controlled values are not rendered through `innerHTML`.
- [x] Critical success and failure events are persisted.
- [x] Core flow runs without model credentials.

## Application-ready gate

- [x] Typed action preview and approval-state UI exist.
- [x] Structured errors include stable codes and trace IDs.
- [x] Concurrency, security, temporal and drift regression tests exist.
- [x] CI runs lint, tests, invariant checks, evaluations and archive smoke.
- [x] CI Docker Compose build and end-to-end smoke are green.
- [x] Generated starter-package artifacts are removed from the public surface.
- [ ] Repository visibility is changed to public after privacy review.
- [ ] A 90-second demo is recorded and linked from the README.
- [x] No unmeasured business result is presented as achieved.
- [x] SkyStudio blueprint remains explicitly unvalidated in a live workspace.

## Optional enhancements

Only after the application-ready gate: optional model narrator, authorized SkyStudio experiment, PostgreSQL/pgvector evaluation, non-production ticketing sandbox or external domain-expert review.
