# Security and Threat Model

## Assets

- Policy content and versions
- Purchase and supplier data
- Approval decisions
- Tool-action payloads
- Idempotency records
- Audit events
- Credentials in a future integration

## Actors

- Procurement Specialist
- Finance Approver
- Solution Engineer
- Auditor
- Malicious or compromised supplier document
- Misconfigured external integration

## Threats and controls

| Threat | Example | Current or planned control | Test |
|---|---|---|---|
| Indirect prompt injection | Supplier file says to ignore rules | Trust metadata, pattern detection, context exclusion | `test_security.py` |
| Stale-policy use | 2025 threshold selected in 2026 | Status and effective-date filter | `test_retrieval.py` |
| Approval bypass | Procurement user triggers write directly | Store-enforced approved state | `test_approvals.py`, `test_api.py` |
| Role escalation | Procurement user approves finance action | Role-action matrix | `test_security.py` |
| Duplicate action | Network retry creates second ticket | Unique idempotency key | `test_idempotency.py` |
| Tool-parameter manipulation | Model changes amount or target | Typed action preview and server-side payload construction | Planned |
| Citation mismatch | Explanation cites wrong section | Structured citation tests | Planned |
| Secret leakage | API token logged | Environment-based secrets and redaction | Planned |
| PII leakage | User data in verbose logs | Synthetic data now; redaction policy later | Planned |
| Retry storm | 503 causes unbounded calls | Bounded exponential backoff | Planned |
| Audit tampering | Event removed or rewritten | Append-oriented event policy; stronger store later | Partially implemented |
| Hallucinated decision | Narrator changes status | Narrator receives immutable structured decision | Current architecture |

## Security invariants

1. Document content is data, never an instruction channel.
2. Authorization runs server-side.
3. Approval is a persisted domain state, not a UI flag.
4. Idempotency is enforced by the receiving integration.
5. A model cannot create or approve a write action.
6. Error details must not contain secrets.
7. Every security-relevant denial should become an audit event in the application-ready release.

## Residual risk

The starter uses pattern-based injection detection and demo headers rather than comprehensive content isolation and real identity. These are acceptable only for the local synthetic PoC.
