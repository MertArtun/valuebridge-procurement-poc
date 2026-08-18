# ADR-001 — Deterministic Policy Engine

## Status

Accepted

## Context

Financial thresholds, date validity, role checks and write permissions require reproducible outcomes.

## Decision

Implement these decisions in normal application code and configuration. A language model may explain but cannot change the result.

## Alternatives considered

- Prompt-only policy reasoning
- Model tool-calling with unrestricted decision authority

## Consequences

Rules are testable and auditable, but policy changes require controlled configuration updates.
