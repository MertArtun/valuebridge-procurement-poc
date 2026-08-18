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
