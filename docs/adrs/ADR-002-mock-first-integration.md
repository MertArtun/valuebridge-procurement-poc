# ADR-002 — Mock-First Enterprise Integration

## Status

Accepted

## Context

A real Jira or ERP credential would slow the application sprint and introduce data and access risks.

## Decision

Use an independent MockDesk HTTP service with an enterprise-shaped contract and idempotency behavior.

## Consequences

The integration pattern is demonstrable without claiming access to a customer system. A later adapter can replace the boundary.
