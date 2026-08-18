# Forward-Deployed Case Study

## Positioning

This case is designed to demonstrate the complete thought process of a forward-deployed Solution Engineer: discover the workflow, identify the risky handoffs, scope a narrow PoC, build the critical path, validate it, define pilot metrics and prepare handoff.

The role framing follows the public forward-deployed engineering pattern: field process discovery, deployment ownership and measurable outcomes.

## Synthetic field-discovery statement

This document is a synthetic field-discovery simulation for an independent portfolio case study. It does not represent an actual SKYMOD customer engagement.

## Stakeholders

| Stakeholder | Need | Risk | ValueBridge response |
|---|---|---|---|
| Procurement Lead | Faster, consistent exception review | Manual calculations and missing documents | Deterministic analysis and evidence |
| Finance Approver | Complete, reviewable request | Incomplete approval packages | Action preview and explicit approval |
| Information Security | Controlled data and tool access | Prompt injection and leakage | Trust classification and role filters |
| Customer IT | Integrable and supportable solution | Duplicate writes and opaque failures | API contract, idempotency and audit |
| Solution Engineer | Demonstrable PoC and handoff | Scope growth and weak acceptance criteria | Locked vertical slice and release gates |

## As-is process

```text
Purchase need
→ Email or form
→ Manual PDF policy search
→ Spreadsheet price analysis
→ Supplier-document check
→ Finance approval over email
→ Manual Jira/ERP entry
→ Follow-up across systems
```

### Observed pain points

1. Employees may use an outdated policy copy.
2. Price and lead-time analysis is manually recreated.
3. Supplier document validity is checked inconsistently.
4. Approval context is spread across email threads.
5. Write actions lack a standardized preview.
6. Retried operations may create duplicate records.
7. There is no unified trace from source to decision to action.

## To-be process

```text
Structured request
→ Role check
→ Effective-policy retrieval
→ Deterministic data analysis
→ Deterministic policy decision
→ Evidence-backed explanation
→ Human action preview
→ Finance approval
→ Idempotent API action
→ Audit and measurement
```

## Human–AI–system boundary

| Step | Owner |
|---|---|
| Interpret the user's request | Optional model or structured form |
| Select accessible current policy | Application retrieval logic |
| Calculate median and variance | Deterministic Python |
| Validate dates and thresholds | Deterministic policy engine |
| Explain the result | Template now; optional model later |
| Approve finance action | Human finance approver |
| Create ticket | MockDesk API after validation |
| Prevent duplicate | Idempotency store |
| Reconstruct outcome | Audit trail |

## Discovery questions to use in an interview or demo

- What triggers the exception process?
- Which request fields are mandatory?
- Where is the authoritative policy stored?
- How are policy versions and effective dates managed?
- Which thresholds require which approvers?
- Which documents must be valid on the request date?
- Which system receives the final action?
- What constitutes a duplicate request?
- Which errors may be retried safely?
- What data may be sent to a model or third-party API?
- Who owns adoption, support and process changes after pilot?
- Which baseline metrics exist today?

## Requirement traceability sample

| Pain point | Requirement | Component | Test | Demo moment |
|---|---|---|---|---|
| Old policy may be used | Select effective `CURRENT` policy | `PolicyRepository` | `test_retrieval.py` | Current/superseded badge |
| Spreadsheet calculations vary | Decimal median and variance | `analysis.py` | `test_analysis.py` | 184,500 and 19.2% |
| Approval is ambiguous | Explicit approval record | `store.py` | `test_approvals.py` | Approve button |
| Retries create duplicates | Idempotency key | MockDesk store | `test_idempotency.py` | Repeat execute |
| Supplier content may manipulate AI | Untrusted-content classification | `security.py` | `test_security.py` | Injection evidence |

## Forward-deployment lifecycle

```text
Discover
→ Map
→ Scope
→ Build
→ Validate
→ Shadow Mode
→ Controlled Pilot
→ Measure
→ Handoff
→ Product Feedback
```

## Pilot design

### Shadow mode

The workflow produces a decision and action preview but performs no write. Its result is compared with the human process.

### Controlled pilot

- One category: `SPARE_PARTS`
- One exception type
- Named procurement and finance users
- Mock or non-production integration
- Mandatory human approval
- Daily issue review
- Weekly acceptance review

### Handoff package

- Architecture and module boundaries
- Data sources and ownership
- Policy and prompt versions
- API and error behavior
- Approval and role model
- Evaluation report
- Known limitations
- Support and escalation path
- Rollback and manual fallback

## Field-feedback record

Each field observation should be captured as:

```text
Observation
Evidence
Customer impact
Current workaround
Reusable pattern
Potential product improvement
Severity
Owner
Decision
```
