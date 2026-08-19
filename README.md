# ValueBridge — Forward-Deployed Procurement AI Case Study

> From process discovery to a measurable, human-approved enterprise workflow.

ValueBridge is a bounded, production-minded portfolio PoC showing how a Solution Engineer can turn an ambiguous operational process into an explainable, controlled and testable AI-assisted workflow.

## Türkçe özet

Kurgusal EgeMekanik A.Ş. için 220.000 TL tutarındaki satın alma talebi incelenir. Sistem talep tarihinde geçerli politikayı seçer, yalnızca o tarihe kadar tamamlanmış satın alma kayıtlarından kategori medyanını hesaplar, fiyat sapmasını bulur, teklif ve sertifika kontrollerini yürütür ve gerekli finans onayını oluşturur. Açık insan onayından sonra MockDesk üzerinde atomik ve payload-aware idempotency ile ticket açılır; bütün kritik adımlar audit trail'e kaydedilir.

Bu çalışma bağımsız bir portföy projesidir. Gerçek SKYMOD ürünü, müşteri deployment'ı veya ölçülmüş iş sonucu değildir.

## Hero result

| Signal | Deterministic result |
|---|---:|
| Request amount | 220,000 TRY |
| Historical median | 184,500 TRY |
| Variance | 19.2% |
| Required quotes | 2 |
| Received quotes | 1 |
| ISO 9001 expiry | 2026-06-30 |
| Request date | 2026-08-18 |
| Decision | `CONDITIONAL_REVIEW` |
| Policy citations | PROC-POL-2026 §4.2, §4.3; SUP-COMP-2026 §3.1 |

## Why this project exists

The target role is not limited to building a chatbot. It requires process discovery, requirements analysis, PoC delivery, enterprise integrations, deployment troubleshooting, onboarding and measurable outcomes. ValueBridge makes those capabilities inspectable in one narrow workflow:

```text
Process Discovery
→ Effective Policy Retrieval
→ Deterministic Analysis
→ Evidence-Backed Decision
→ Action Preview
→ Human Approval
→ Idempotent Enterprise Action
→ Audit
```

## Verified system behavior

The repository tests and invariant checks cover:

- Current-policy selection with explicit rejection of request dates outside the effective window
- Section-level citations and policy/runtime threshold alignment
- Decimal-based median and variance calculations using only prior purchases
- Supplier certificate, quote-count and finance-threshold rules
- Explicit approval state machine with rejection and expiry
- Approval reuse on an identical re-analysis and supersede after a corrected one
- Atomic approve/reject transitions under concurrency
- Atomic, payload-aware idempotent ticket creation under concurrency
- Bounded retry/backoff with safe `Retry-After` handling
- Quarantine of untrusted supplier instructions
- Structured domain errors with trace IDs and failure audit events
- Denied and blocked approval and execution attempts recorded as traced audit events
- Approve and reject controls that stay disabled until the action preview loads
- Safe DOM rendering without API-controlled `innerHTML`
- Browser security headers and Docker build-context exclusions

These checks validate system behavior, not customer ROI or production impact.

## Architecture

```text
Browser
  → FastAPI ValueBridge
      → Effective policy repository
      → Purchase-history analysis
      → Deterministic policy engine
      → Approval state store
      → Audit store
      → MockDesk HTTP API
          → Atomic idempotency store
```

Critical decisions never depend on model output. An optional model can later narrate a locked decision, but it cannot alter rule results, authorization, approval state or tool parameters.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ruff check .
pytest -q
python scripts/verify.py
python scripts/run_evals.py
```

Run MockDesk:

```bash
uvicorn mockdesk.main:app --port 8001
```

Run ValueBridge in another terminal:

```bash
MOCKDESK_URL=http://127.0.0.1:8001 uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000`.

Docker alternative:

```bash
docker compose up --build
```

After both services are available, run the assertion-based end-to-end demo:

```bash
bash scripts/demo.sh
```

## Repository map

```text
app/          ValueBridge API, domain logic, UI and persistence
mockdesk/     Independent mock enterprise ticketing service
data/         Synthetic policies, suppliers and purchase history
tests/        Behavioral, security and concurrency tests
docs/         PRD, architecture, FDE case, security and delivery plan
evals/        Frozen evaluation cases and independent policy oracle
scripts/      Verification, evaluation and end-to-end demo helpers
```

## Security and reliability boundaries

- Browser input and supplier attachments are untrusted.
- API values are rendered through DOM `textContent`, not HTML injection.
- Retrieval filters by trust, role, type and effective date before returning content.
- The LLM boundary never owns calculations, policy rules, approval or idempotency.
- All write actions require an approved record.
- The idempotency key is scoped to the approved action instance, so a corrected re-analysis gets a fresh key instead of a permanent conflict.
- The idempotency key is bound to a canonical payload hash.
- Same key and same payload returns the original ticket.
- Same key and different payload returns `IDEMPOTENCY_CONFLICT`.
- Retry attempts reuse the same idempotency key and are bounded.

See [`docs/07_SECURITY_THREAT_MODEL.md`](docs/07_SECURITY_THREAT_MODEL.md) and [`docs/05_ARCHITECTURE.md`](docs/05_ARCHITECTURE.md).

## SkyStudio status

The workflow blueprint is based on publicly available SkyStudio product and API documentation. It has not been validated inside an authorized SkyStudio workspace and is not presented as a completed integration. See [`docs/09_SKYSTUDIO_WORKFLOW_BLUEPRINT.md`](docs/09_SKYSTUDIO_WORKFLOW_BLUEPRINT.md).

## Known limitations

- Synthetic field-discovery and operational data
- Demo headers instead of production identity/SSO
- File-backed policy repository instead of governed enterprise knowledge infrastructure
- SQLite rather than managed PostgreSQL
- Pattern-based injection detection rather than a complete content-security system
- Mutable local audit storage rather than immutable enterprise audit infrastructure
- No live SkyStudio, Jira or ERP workspace
- No measured adoption, ROI or cycle-time result

## Independent project notice

This repository is not an official SKYMOD product and is not endorsed by SKYMOD. SKYMOD and SkyStudio trademarks belong to their respective owner. EgeMekanik A.Ş., Atlas Endüstri and all operational data are synthetic.
