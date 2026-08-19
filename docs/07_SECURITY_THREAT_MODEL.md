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
| Injection through free-text intake | The text is data: a matched rule is flagged on the draft and audited, the draft still needs human review and never starts an analysis | `test_intake.py` |
| Retrieval poisoning through a supplier attachment | Trust, role and effective-date filters run before scoring, so untrusted content is not a candidate at any rank | `test_policy_qa.py`, `RAG-002` |
| Superseded policy resurfacing through relevance | Status and effective window are candidate filters, not ranking features | `test_policy_qa.py`, `RAG-001` |
| Model output steering a decision | Narration runs after the decision is persisted and enters no fingerprint; decision fields are identical with the layer on or off | `test_llm_narrator.py` |
| Provider key or prompt leaking through an error | The key is read from the environment only; provider failures surface as a status code or exception class, never the response body | `test_llm_client.py` |
| Ambient credentials changing what CI proves | An autouse fixture clears the provider variables for every test | `test_llm_env_isolation.py` |

## The realized model boundary

The model layer exists and is used, so its boundary is stated as implemented rather than as an intention.

**What reaches the model.** Untrusted content does reach it: supplier attachment text is excluded from retrieval, and free-text intake is user input of unknown origin. Both are handed over as data inside a delimited prompt. Nothing the model reads becomes an instruction to the application, because the application never parses model output for commands — it parses it for a draft request that a human then reviews, or it renders it as text.

**What the model may produce.** Three display-only surfaces: an intake draft, a narrative for an already locked decision and an answer built from sections retrieval has already governed. None of them is an input to a rule, an authorization check, an approval state, an idempotency key or a tool payload. Turning the layer off changes only whether those fields are populated.

**How the secret is handled.** The API key is read from `VALUEBRIDGE_LLM_API_KEY` at client construction and is never logged, echoed or persisted. Provider transport failures are reported by exception class and HTTP failures by status code alone, because a provider body can echo the prompt or internal details.

**What the trail records.** A matched injection pattern is stored on `INTAKE_DRAFTED` as `injection_rule_id` and on the policy-question event, so an attempt is visible even though it changed nothing. Disabled and failed model calls emit `INTAKE_FAILED` or `NARRATION_SKIPPED` with a code, never with content.

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
