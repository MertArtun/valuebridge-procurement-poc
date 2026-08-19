from __future__ import annotations

from datetime import datetime
from statistics import median

from app.models import AuditEvent

_DENIED_OR_BLOCKED = {
    "AUTHORIZATION_DENIED",
    "APPROVAL_DENIED",
    "TOOL_EXECUTION_DENIED",
    "TOOL_EXECUTION_BLOCKED",
}
_APPROVAL_OUTCOMES = {
    "APPROVAL_GRANTED": "granted",
    "APPROVAL_REJECTED": "rejected",
    "APPROVAL_EXPIRED": "expired",
    "APPROVAL_SUPERSEDED": "superseded",
}


def summarize(events: list[AuditEvent]) -> dict[str, object]:
    """Derive pilot metrics from the audit trail; the trail is the instrument."""
    decisions = {"APPROVED": 0, "CONDITIONAL_REVIEW": 0, "REJECTED": 0}
    approvals = {"granted": 0, "rejected": 0, "expired": 0, "superseded": 0}
    tickets_created = 0
    duplicates_prevented = 0
    quarantined_attachments = 0
    denied_or_blocked_actions = 0
    started: dict[str, datetime] = {}
    completed: dict[str, datetime] = {}

    for event in events:
        if event.event_type == "POLICY_EVALUATED":
            status = str(event.details.get("decision_status", ""))
            if status in decisions:
                decisions[status] += 1
        elif event.event_type == "REQUEST_RECEIVED":
            if event.request_id and event.request_id not in started:
                started[event.request_id] = event.timestamp
        elif event.event_type == "TOOL_EXECUTED":
            if event.details.get("status") == "ALREADY_PROCESSED":
                duplicates_prevented += 1
            elif event.details.get("status") == "OPEN":
                tickets_created += 1
                if event.request_id and event.request_id not in completed:
                    completed[event.request_id] = event.timestamp
        elif event.event_type == "SECURITY_CONTENT_QUARANTINED":
            quarantined_attachments += 1
        elif event.event_type in _DENIED_OR_BLOCKED:
            denied_or_blocked_actions += 1
        elif event.event_type in _APPROVAL_OUTCOMES:
            approvals[_APPROVAL_OUTCOMES[event.event_type]] += 1

    cycle_times = [
        (completed[request_id] - started[request_id]).total_seconds()
        for request_id in completed
        if request_id in started
    ]
    return {
        "analyses_total": sum(decisions.values()),
        "decisions": decisions,
        "approvals": approvals,
        "tickets_created": tickets_created,
        "duplicates_prevented": duplicates_prevented,
        "quarantined_attachments": quarantined_attachments,
        "denied_or_blocked_actions": denied_or_blocked_actions,
        "completed_requests": len(cycle_times),
        "median_cycle_time_seconds": round(median(cycle_times), 3) if cycle_times else None,
    }
