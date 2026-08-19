# Data and Policy Specification

## Synthetic-data boundary

All organizations, suppliers, policies and transactions in this repository are synthetic. They do not describe a real customer deployment.

## Hero constants

| Field | Value |
|---|---:|
| Request ID | PR-2026-0042 |
| Request date | 2026-08-18 |
| Amount | 220,000 TRY |
| Category | SPARE_PARTS |
| Supplier | Atlas Endüstri |
| Historical median | 184,500 TRY |
| Received / required quotes | 1 / 2 |
| ISO expiry | 2026-06-30 |
| Standard / offered lead time | 14 / 20 days |

## Document metadata

`data/documents.json` records document ID, type, version, lifecycle status, effective period, replacement relationship, role allowlist, trust flag and file path. Retrieval filters by trust, role, type and effective period before returning content. The PoC serves only `CURRENT` documents inside their effective window; the superseded 2025 policy stays in the corpus as a stale-policy exclusion fixture and request dates outside the current window fail with an explicit error.

## Rule sources

- `data/policy_rules.yaml` is the runtime configuration.
- `evals/policy_oracle.yaml` is the independent evaluation oracle.
- Human-readable policy Markdown is checked against runtime thresholds by `scripts/verify.py` and regression tests.

Application runtime never imports the evaluation oracle.

## Purchase-history boundary

Only `COMPLETED` rows in the request category whose `purchase_date` is on or before `request_date` enter the median. The hero dataset must remain exactly 184,500 TRY; a backdated regression verifies future purchases are excluded.

## Untrusted content

`data/supplier_attachment_untrusted.md` intentionally contains prompt-injection language. The attachment is scanned as untrusted evidence, excluded from policy retrieval and citations, and represented in audit only by document ID and matched rule ID—not by the malicious text.

## Local retention

SQLite files remain until the runtime volume or files are removed. A real deployment would define retention, deletion and legal-hold rules by customer policy and data class.
