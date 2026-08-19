# Security and Threat Model

## Assets and actors

Protected assets include policy versions, purchase/supplier data, approval decisions, tool payloads, idempotency records and audit events. Actors are Procurement Specialist, Finance Approver, Solution Engineer, Auditor, untrusted supplier content and the external integration boundary.

## Threats and controls

| Threat | Control | Evidence |
|---|---|---|
| Indirect prompt injection | Trust metadata, quarantine event and context exclusion | `test_prompt_injection_quarantine.py` |
| Wrong policy version | Role/trust/effective-period selection | `test_retrieval.py`, `test_application_readiness.py` |
| Approval bypass | Persisted approval state checked server-side | `test_approvals.py`, `test_api.py` |
| Approval race | Immediate transaction and compare-and-set terminal transition | `test_concurrency_hardening.py` |
| Role escalation | Server-side role/action matrix | `test_security.py` |
| Duplicate action | Atomic idempotency key plus canonical payload hash | `test_concurrency_hardening.py` |
| Changed payload replay | `409 IDEMPOTENCY_CONFLICT` | `test_concurrency_hardening.py` |
| Tool-parameter manipulation | Server-generated typed action preview | `test_action_preview.py` |
| Citation drift | Rule-to-section mapping and policy/rule invariant | `test_api.py`, `test_application_readiness.py` |
| DOM injection | DOM node construction, `textContent`, CSP and schema bounds | `test_ui.py`, `test_ui_security_hardening.py` |
| Secret copied into image | `.dockerignore`, no core credentials and non-root image | `test_ui_security_hardening.py` |
| Retry storm | Three-attempt retry, bounded `Retry-After` and preserved key | `test_mockdesk_retry.py`, `test_retry_after_hardening.py` |
| Audit deletion or rewrite | Append-oriented local events; immutable store remains a production replacement | Residual risk |

## Security invariants

1. Document content is data, never an instruction channel.
2. Authorization runs server-side.
3. Approval is persisted domain state, not a UI flag.
4. Exactly one terminal approval transition succeeds.
5. Idempotency is enforced by the receiving integration.
6. A model cannot create or approve a write action.
7. API-controlled text is not interpreted as markup.
8. Security quarantines and domain-analysis failures emit traceable audit events.

## Residual risks

Demo headers are not production identity, regex detection is not complete content isolation, SQLite audit records are mutable and the file-backed repository is not a governed enterprise knowledge system. These limits are stated rather than hidden.
