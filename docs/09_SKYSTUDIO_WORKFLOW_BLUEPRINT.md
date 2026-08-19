# SkyStudio Workflow Blueprint

## Status

Designed from publicly available SkyStudio product and API documentation. Not validated inside an authorized SkyStudio workspace.

This is a platform-mapping exercise, not a completed integration.

## Why this document exists

The target role emphasizes building enterprise deployments through workflow and agent modules. The strongest proof without workspace credentials is a precise mapping of business steps, data contracts, deterministic services, human decisions and API boundaries.

## Proposed workflow

| Order | Logical step | Responsibility | Candidate SkyStudio concept | External/custom need |
|---:|---|---|---|---|
| 1 | Request trigger | Receive purchase request | Workflow start/API trigger | Request schema |
| 2 | User context | Resolve role and identity | API/data lookup | Identity service |
| 3 | Current policy retrieval | Retrieve accessible effective policy | Assistant/RAG/knowledge source | Metadata and ACL policy |
| 4 | Purchase-history query | Load category history | HTTP/API node | Data service |
| 5 | Deterministic analysis | Median, variance, lead time | HTTP/custom-code service | ValueBridge analysis API |
| 6 | Supplier validation | Certificate and risk data | HTTP/API node | Supplier service |
| 7 | Policy evaluation | Apply thresholds | Condition nodes or external API | ValueBridge policy API |
| 8 | Explanation | Present evidence and reasons | Agent/assistant | Structured decision input |
| 9 | Action preview | Display outbound payload | Form/chat response | Typed preview schema |
| 10 | Human approval | Capture explicit decision | Approval pattern using available form/webhook capability | Workspace validation required |
| 11 | Ticket action | Create external record | HTTP/API or Jira connector | Idempotency header |
| 12 | Audit | Record inputs and output | API/webhook | Audit service |
| 13 | Failure branch | Retry, fallback and escalation | Workflow conditions | Error policy |

## Node-level mapping

The table above is the business view. This one is the build view: which SkyStudio construct carries each step and which ValueBridge endpoint it calls. Endpoint paths, methods and status codes are real and testable today; the SkyStudio column is the design target and is unvalidated.

| # | Step | SkyStudio construct | ValueBridge call | Contract detail |
|---:|---|---|---|---|
| 1 | Collect the request in chat | Assistant (`Satın Alma Asistanı`) | — | System prompt states that it collects fields and never decides |
| 2 | Turn free text into a draft | Assistant tool → webhook | `POST /api/v1/requests/intake` | Body `{"text": "..."}`; returns `draft`, `missing_fields`, `injection_rule_id`, `trace_id` |
| 3 | Ask for the missing fields | Assistant turn | — | Loops on `missing_fields`; no call until the draft is complete |
| 4 | Confirm the draft with the user | Assistant turn | — | The human, not the model, approves the draft that gets analyzed |
| 5 | Run the decision | Workflow node (HTTP) | `POST /api/v1/requests/analyze` | Headers `X-Demo-Role`, `X-Demo-User`; returns `analysis`, `decision`, `citations`, `approval`, `llm_narrative` |
| 6 | Branch on the outcome | Workflow condition node | — | On `decision.decision_status`: `APPROVED`, `CONDITIONAL_REVIEW`, `REJECTED` |
| 7 | End a rejected request | Workflow end node | — | `REJECTED` carries no `approval`; the branch closes with the citation, it does not route for sign-off |
| 8 | Show the outbound payload | Workflow node (HTTP) → assistant message | `GET /api/v1/approvals/{id}/action-preview` | The preview is server-generated; the assistant renders it verbatim |
| 9 | Collect the finance decision | Approval pattern over the available form/webhook capability | `POST /api/v1/approvals/{id}/approve` or `/reject` | Requires the `finance_approver` role; needs workspace validation |
| 10 | Create the ticket | Workflow node (HTTP) or Jira connector | `POST /api/v1/tool-actions/{id}/execute` | Returns `409 APPROVAL_REQUIRED` if called before sign-off; replay returns the same `ticket_id` with `ALREADY_PROCESSED` |
| 11 | Answer a policy question | Agent tool → webhook | `POST /api/v1/policies/ask` | Body `{"question": "...", "on_date": "YYYY-MM-DD"}`; returns governed `sections` plus an optional `answer` |
| 12 | Report the pilot | Scheduled workflow → webhook | `GET /api/v1/metrics/summary` | Derived from the audit trail; safe to post into a channel |
| 13 | Handle failure | Workflow error branch | — | Retry on `502`; stop on `409`; surface `503 LLM_DISABLED` as "assistant unavailable, use the form" |

## Target architecture

The intake assistant is the piece that belongs in SkyStudio rather than in ValueBridge. It is a SkyStudio assistant that owns the conversation and calls ValueBridge as a tool:

```text
User (chat)
  → SkyStudio assistant
      → tool: ValueBridge POST /requests/intake      (draft, missing fields, injection flag)
      ← assistant asks for what is missing
      → human confirms the draft
      → tool: ValueBridge POST /requests/analyze     (decision, citations, approval)
  → SkyStudio workflow
      → action preview → finance approval → execute → audit
```

The split is deliberate. The assistant owns turn-taking, clarification and phrasing, which is what a conversational platform is good at. ValueBridge owns the arithmetic, the effective policy, the approval state and the idempotency key, which are the parts that must be identical on every run and must survive the model being unavailable. If the assistant is switched off, the same workflow still runs from the form.

## Accuracy boundary

The public Workflow API documentation confirms that a published workflow can be triggered by `POST /api/workflow/workflowrun` with Bearer authentication. Public status-code guidance recommends `Retry-After`, exponential backoff, idempotent requests and safe fallback patterns. This blueprint does not assert a native approval node; the exact human-approval implementation must be validated in an authorized workspace.

## LLM versus deterministic work

### Agent/assistant

- Summarize the decision
- Explain citations
- Ask for missing non-authoritative information

### External deterministic service

- Calculate financial values
- Select effective rules
- Validate certificate date
- Authorize roles
- Enforce approval state
- Build and validate tool payload
- Enforce idempotency

## Integration status language

Acceptable:

> The workflow is mapped to public SkyStudio concepts and API contracts; live workspace validation is pending authorized access.

Not acceptable:

> Fully integrated with SkyStudio.

## Official references

- https://docs.skymod.tech/en/workflow-api
- https://docs.skymod.tech/en/status-codes
- https://skymod.ai/careers/solution-engineer
- https://skymod.ai/what-s-new-in-skystudio
