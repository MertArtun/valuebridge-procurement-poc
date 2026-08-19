# Pilot Metrics Plan

## Principle

The audit trail is the measurement instrument. Every metric below is derived from
recorded audit events, never from self-reported numbers. `GET /api/v1/metrics/summary`
computes the current values at any time, and the same derivation would run against a
pilot deployment without extra instrumentation.

All values produced by this repository come from synthetic demo data. They demonstrate
the measurement mechanism, not a customer outcome.

## Metrics derived today

| Metric | Source events | Why it matters |
|---|---|---|
| Decision distribution | `POLICY_EVALUATED` | Shows how often the workflow approves, escalates or rejects. |
| Median cycle time | first `REQUEST_RECEIVED` → first successful `TOOL_EXECUTED` per request | The headline speed number for an exception review. |
| Tickets created | `TOOL_EXECUTED` with status `OPEN` | Completed enterprise actions. |
| Duplicates prevented | `TOOL_EXECUTED` with status `ALREADY_PROCESSED` | Direct evidence the idempotency layer removes duplicate work. |
| Quarantined attachments | `SECURITY_CONTENT_QUARANTINED` | Untrusted supplier content stopped before it can influence anything. |
| Denied or blocked attempts | `AUTHORIZATION_DENIED`, `APPROVAL_DENIED`, `TOOL_EXECUTION_DENIED`, `TOOL_EXECUTION_BLOCKED` | Control effectiveness: unauthorized or premature actions never reach the target system. |
| Approval outcomes | `APPROVAL_GRANTED` / `REJECTED` / `EXPIRED` / `SUPERSEDED` | Health of the human-approval loop. |

## What a real pilot would add

1. **Baseline capture.** Before go-live, sample 20–30 historical exception reviews and
   record manual cycle time, rework count and policy-version errors from tickets and
   email threads. Without a baseline there is no defensible before/after claim.
2. **Business KPIs on top of system metrics.** First-pass approval rate, share of
   requests citing the current policy version, duplicate-ticket rate in the ticketing
   system, and reviewer minutes per request.
3. **Adoption metrics.** Weekly active reviewers, share of exceptions routed through
   the workflow versus around it.
4. **Review cadence.** A weekly metric review with the process owner during the pilot,
   with acceptance thresholds agreed before the pilot starts.

## Explicit non-claims

No adoption, ROI or cycle-time improvement is claimed anywhere in this repository.
The pilot plan defines how those numbers would be measured; it does not assert them.
