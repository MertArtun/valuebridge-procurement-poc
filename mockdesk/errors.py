from __future__ import annotations


class MockDeskError(Exception):
    code = "MOCKDESK_ERROR"
    status_code = 400
    retryable = False


class IdempotencyConflictError(MockDeskError):
    code = "IDEMPOTENCY_CONFLICT"
    status_code = 409
