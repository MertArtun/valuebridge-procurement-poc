# Product Requirements Document — ValueBridge

## 1. Document control

| Field | Value |
|---|---|
| Product | ValueBridge — Forward-Deployed Procurement AI Case Study |
| Release target | Application-ready portfolio PoC |
| Current repository state | Starter vertical slice |
| Primary language | Turkish UI and documentation; English identifiers |
| Customer | EgeMekanik A.Ş. — synthetic |
| Hero supplier | Atlas Endüstri — synthetic |

## 2. Product vision

ValueBridge demonstrates how a Solution Engineer converts a fragmented procurement exception process into a controlled, explainable and measurable AI-assisted workflow without delegating financial authority or enterprise write permissions to an LLM.

## 3. Problem statement

The synthetic as-is process requires employees to search policies manually, calculate price comparisons in spreadsheets, inspect supplier documents, request approvals through email and then re-enter data into a ticketing or ERP system. The process creates risks around stale policy use, arithmetic errors, missing evidence, approval ambiguity, duplicate records and weak auditability.

## 4. Product thesis

A bounded workflow with deterministic decision controls, evidence-backed explanation, explicit human approval, idempotent integration and end-to-end audit is a stronger enterprise AI demonstration than a general-purpose chatbot.

## 5. Goals

- Show process discovery and requirement translation.
- Analyze the hero purchase request with reproducible results.
- Use the policy effective on the request date.
- Separate deterministic decisions from language-model narration.
- Require explicit approval before every write action.
- Demonstrate an HTTP enterprise integration through MockDesk.
- Prevent duplicate ticket creation.
- Expose evidence suitable for troubleshooting and audit.
- Define system-quality and workflow-impact measurements separately.
- Remain runnable without external credentials.

## 6. Non-goals

- Autonomous purchasing or payment
- A generic procurement product
- A workflow-canvas builder
- Real Jira, ERP or SkyStudio integration
- Production SSO, multi-tenancy or cloud infrastructure
- A generalized multi-agent framework
- Business-impact claims based on synthetic data

## 7. Personas

### Procurement Specialist

Creates and analyzes requests, reviews evidence and executes an approved ticket action. Cannot approve the finance action.

### Finance Approver

Reviews the action preview and approves or rejects the finance action. Does not alter deterministic policy rules.

### Solution Engineer

Configures the scenario, validates integrations, inspects audit evidence, demonstrates the PoC and translates field findings into product feedback.

### Auditor

Reads the event trail and verifies policy version, decision inputs, approval and tool execution. Cannot create or approve requests.

## 8. Jobs to be done

- When a high-value purchase request arrives, determine which current policies apply and what evidence is missing.
- When a write action is proposed, show exactly what will be sent and require the correct human approval.
- When an external call is retried, avoid duplicate records.
- When a result is challenged, reconstruct the decision from source version, inputs, rules, approval and tool output.
- When a customer process changes, identify which requirements, rules, tests and demo steps must change.

## 9. Hero workflow

```text
Purchase Request
→ Role Check
→ Current Policy Retrieval
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

## 10. Functional requirements

| ID | Requirement | Priority | Acceptance evidence |
|---|---|---|---|
| FR-001 | The system shall accept the fixed hero request through API and UI. | Must | API and UI tests |
| FR-002 | The system shall verify that the actor may analyze a request. | Must | Authorization test |
| FR-003 | The system shall select the policy effective on the request date. | Must | Version-selection test |
| FR-004 | The system shall exclude superseded policy from the final decision. | Must | Stale-policy test |
| FR-005 | The system shall filter documents by role before content is returned. | Must | ACL test |
| FR-006 | The system shall calculate category median from completed purchases. | Must | Median test |
| FR-007 | The system shall calculate exact and display price variance using Decimal arithmetic. | Must | Analysis test |
| FR-008 | The system shall check supplier certificate validity against request date. | Must | Policy test |
| FR-009 | The system shall check finance approval threshold. | Must | Policy test |
| FR-010 | The system shall check alternative-quote threshold and count. | Must | Policy test |
| FR-011 | The system shall produce a structured `PolicyDecision`. | Must | Schema and policy tests |
| FR-012 | The system shall cite the policy document, version and section used. | Must | Citation test |
| FR-013 | The system shall create a pending approval for write actions. | Must | Approval test |
| FR-014 | The system shall block execution until approval is explicit. | Must | API conflict test |
| FR-015 | Only a finance approver shall approve the finance action. | Must | Authorization test |
| FR-016 | The system shall show the outbound action payload before execution. | Must | Action-preview test |
| FR-017 | The system shall send the approved action to MockDesk over HTTP. | Must | Contract test |
| FR-018 | The system shall use an idempotency key derived from request and action. | Must | Idempotency test |
| FR-019 | Repeated execution shall return the original ticket without creating a duplicate. | Must | Idempotency test |
| FR-020 | The system shall record request, retrieval, analysis, decision, approval and tool events. | Must | Audit test |
| FR-021 | Untrusted supplier instructions shall be classified and excluded from trusted policy context. | Must | Injection test |
| FR-022 | A detected injection attempt shall create a security audit event. | Should | Security-event test |
| FR-023 | The UI shall display analysis, reasons, citations, approval and audit states. | Must | UI test |
| FR-024 | The evaluation runner shall export machine-readable results. | Should | Evaluation-runner test |
| FR-025 | The project shall expose an optional model-provider boundary without requiring credentials. | Could | Provider contract test |

## 11. Non-functional requirements

| ID | Category | Requirement | Target |
|---|---|---|---|
| NFR-001 | Reliability | Duplicate writes with the same idempotency key | 0 |
| NFR-002 | Security | Write actions without approved record | 0 |
| NFR-003 | Security | Unauthorized policy-content disclosure | 0 successful cases |
| NFR-004 | Correctness | Hero median | Exactly 184,500 TRY |
| NFR-005 | Correctness | Hero exact variance | Exactly 19.2412% |
| NFR-006 | Audit | Critical workflow events | All defined events present |
| NFR-007 | Portability | External credentials for core flow | None required |
| NFR-008 | Operability | Local startup | Documented venv and Docker paths |
| NFR-009 | Testability | Behavioral changes | Failing test before implementation |
| NFR-010 | Explainability | Decision reasons | Structured reasons and citations |
| NFR-011 | Maintainability | Module boundaries | One clear responsibility per module |
| NFR-012 | Privacy | Real customer data | None in repository |
| NFR-013 | Truthfulness | Unmeasured business metrics | Not presented as achieved |
| NFR-014 | Accessibility | Core workflow | Keyboard-usable controls and readable contrast |

## 12. Evidence model

Every decision-relevant requirement should map to:

```text
Evidence source
→ Requirement
→ Component
→ Test
→ Demo segment
```

The starter includes authored policy evidence. A later discovery panel may add `DIRECT_STATEMENT`, `PARAPHRASE` and `INFERENCE` evidence types, but it is not required for the initial application-ready gate.

## 13. Decision boundary

### Deterministic components

- Arithmetic
- Date validity
- Policy thresholds
- Role authorization
- Approval state
- Idempotency
- Tool permission

### Language-model-compatible components

- Request normalization
- Natural-language explanation
- Question generation for missing evidence
- Executive summary

A model output may not modify `decision_status`, rule IDs, approval state or tool parameters after validation.

## 14. API surface

Implemented endpoints:

```text
GET  /health
POST /api/v1/requests/analyze
GET  /api/v1/approvals/{approval_id}/action-preview
POST /api/v1/approvals/{approval_id}/approve
POST /api/v1/tool-actions/{approval_id}/execute
GET  /api/v1/audit/events
```

Planned endpoint:

```text
POST /api/v1/approvals/{approval_id}/reject
POST /api/v1/evaluations/run
```

## 15. Error behavior

- `400`: malformed or missing fields
- `403`: role is not authorized
- `404`: request or approval does not exist
- `409`: action requires approval or conflicts with current state
- `429`: follow `Retry-After` and use bounded exponential backoff
- `499`: treat as client cancellation; preserve idempotency for safe retry
- `503/504`: bounded retry and graceful failure with audit event

## 16. UX principles

- Start with the business process, not a chat window.
- Show deterministic values before narrative explanation.
- Make current and superseded policy state visible.
- Preview all write parameters.
- Keep approval and execution separate.
- Surface trace IDs and audit evidence without developer tools.
- Clearly label synthetic scenario and integration limitations.

## 17. Metrics

### System quality

- Policy decision correctness
- Citation-to-section match
- Stale-policy selection count
- Unauthorized access success count
- Approval bypass count
- Duplicate ticket count
- Injection bypass count
- Tool payload schema conformance

### Workflow impact — not measured in this starter

- End-to-end cycle time
- Manual touch count
- Approval turnaround
- Assisted request rate
- Human intervention rate
- Fallback rate
- Adoption and repeat usage
- Estimated time saved

## 18. Release gates

### Starter gate

Core tests pass and the hero API flow works without external credentials.

### Application-ready gate

All Must requirements pass; action preview, failure handling, injection quarantine, evaluation report and polished demo are complete.

### Optional platform gate

A SkyStudio adapter or workspace workflow may be added only after the application-ready gate and only with authorized access.
