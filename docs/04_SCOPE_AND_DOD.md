# Scope and Definition of Done

## Locked core scope

- One synthetic procurement exception scenario
- One current and one superseded procurement policy
- Supplier compliance validation
- Purchase-history analysis
- Deterministic policy engine
- Human finance approval
- MockDesk HTTP integration
- Idempotency
- Role controls
- Audit trail
- Security test for indirect prompt injection
- Local runtime and Docker Compose
- Short demo narrative

## Explicit non-goals

- General procurement SaaS
- Real customer data
- Real purchasing or payment
- Real Jira, ERP or Slack
- Live SkyStudio dependency
- Multi-agent framework
- Workflow builder
- Keycloak, Kubernetes, Terraform, Grafana or cloud deployment
- Advanced vector-RAG infrastructure
- Business-impact claims from synthetic data

## Core Done

- [x] The hero amount is 220,000 TRY.
- [x] The historical median is exactly 184,500 TRY.
- [x] Exact variance is 19.2412%; displayed variance is 19.2%.
- [x] The 2026 policy is selected for the 2026 request.
- [x] The superseded 2025 policy is not used for the decision.
- [x] Finance approval is required.
- [x] The missing alternative quote is detected.
- [x] The expired certificate is detected.
- [x] Tool execution is blocked before approval.
- [x] Only the finance role may approve.
- [x] The same idempotency key creates no second ticket.
- [x] Critical events are persisted in audit storage.
- [x] The core flow runs without model credentials.
- [x] Automated tests cover the hero path.

## Application-ready gate

- [x] Supplier compliance policy appears as a separate citation.
- [x] Action preview has a typed response model and endpoint.
- [x] Approval rejection and expiry are implemented and tested.
- [x] MockDesk HTTP retry/backoff behavior is tested for transient errors.
- [ ] Injection detection quarantines the document and emits an audit event.
- [ ] Evaluation cases run through a reproducible runner.
- [ ] UI displays failure, rejection, duplicate and audit-detail states.
- [ ] `ruff check .`, `pytest -q` and `python scripts/verify.py` are clean.
- [ ] Docker Compose has been executed on a Docker-capable machine.
- [ ] README has final screenshots or a video link.
- [ ] A 90-second demo is recorded without cuts that hide failures.
- [ ] No unmeasured business result is presented as achieved.
- [ ] SkyStudio blueprint remains clearly unvalidated in a live workspace.

## Optional enhancement gate

Only after the application-ready gate:

- Optional OpenAI-compatible narrator
- Authorized SkyStudio workflow experiment
- PostgreSQL/pgvector evaluation
- Real non-production ticketing sandbox
- External domain-expert review
