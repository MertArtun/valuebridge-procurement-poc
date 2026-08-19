from __future__ import annotations


class ValueBridgeError(Exception):
    code = "VALUEBRIDGE_ERROR"
    status_code = 400
    retryable = False

    def __init__(self, message: str, *, trace_id: str | None = None) -> None:
        super().__init__(message)
        self.trace_id = trace_id

    def attach_trace(self, trace_id: str) -> ValueBridgeError:
        self.trace_id = trace_id
        return self


class SupplierNotFoundError(ValueBridgeError):
    code = "SUPPLIER_NOT_FOUND"
    status_code = 404


class PurchaseHistoryNotFoundError(ValueBridgeError):
    code = "PURCHASE_HISTORY_NOT_FOUND"
    status_code = 422


class PurchaseHistoryInvalidError(ValueBridgeError):
    code = "PURCHASE_HISTORY_INVALID"
    status_code = 422


class ApplicablePolicyNotFoundError(ValueBridgeError):
    code = "APPLICABLE_POLICY_NOT_FOUND"
    status_code = 422


class ApprovalRequiredError(ValueBridgeError):
    code = "APPROVAL_REQUIRED"
    status_code = 409


class InvalidApprovalStateError(ValueBridgeError):
    code = "INVALID_APPROVAL_STATE"
    status_code = 409


class AuthorizationError(ValueBridgeError, PermissionError):
    code = "FORBIDDEN"
    status_code = 403


class IdempotencyConflictError(ValueBridgeError):
    code = "IDEMPOTENCY_CONFLICT"
    status_code = 409


class ApprovalContextChangedError(ValueBridgeError):
    code = "APPROVAL_CONTEXT_CHANGED"
    status_code = 409


class MockDeskUnavailableError(ValueBridgeError):
    code = "MOCKDESK_UNAVAILABLE"
    status_code = 502
    retryable = True


class MockDeskRequestError(ValueBridgeError):
    code = "MOCKDESK_REQUEST_FAILED"
    status_code = 502
