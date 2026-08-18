# Data and Policy Specification

## Synthetic-data principle

All data is created for this portfolio project. Names, transactions, policies and suppliers do not describe real organizations.

## Authoritative constants

| Field | Value |
|---|---:|
| Request ID | PR-2026-0042 |
| Request date | 2026-08-18 |
| Amount | 220,000 TRY |
| Category | SPARE_PARTS |
| Supplier | Atlas Endüstri |
| Historical median | 184,500 TRY |
| Received quotes | 1 |
| Required quotes | 2 |
| ISO expiry | 2026-06-30 |
| Supplier quality | 82 |
| Standard lead time | 14 days |
| Offered lead time | 20 days |

## Document metadata

`data/documents.json` defines:

- `document_id`
- `version`
- `status`
- `effective_from`
- `effective_to`
- `superseded_by`
- `allowed_roles`
- `trusted_for_retrieval`
- `file_path`

The application must filter by trust, role, type, status and effective date before returning document text.

## Policy sources

### Operational rule configuration

`data/policy_rules.yaml` is used by the application.

### Independent evaluation oracle

`evals/policy_oracle.yaml` is used by future evaluation tooling. Application code must not import it.

This separation does not make synthetic evaluation independent research; it prevents the runtime from reading expected test outputs directly.

## Purchase-history invariant

For completed `SPARE_PARTS` records, the median must remain exactly 184,500 TRY. `scripts/verify.py` checks this invariant.

## Versioning invariant

- `PROC-POL-2025` is superseded and ends on 2025-12-31.
- `PROC-POL-2026` is current from 2026-01-01.
- The request date is 2026-08-18.
- Therefore the 2026 policy is the only valid procurement decision source.

## Untrusted content

`data/supplier_attachment_untrusted.md` intentionally contains prompt-injection language. It may be displayed as evidence of an attempted attack but must never enter trusted policy context or alter a tool action.

## Retention

The PoC keeps local SQLite records until the runtime files are removed. A production design would define retention by data class, legal requirement and customer policy.
