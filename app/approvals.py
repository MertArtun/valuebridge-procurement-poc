class ApprovalRequiredError(RuntimeError):
    """Raised when a write action is attempted without explicit approval."""


class InvalidApprovalStateError(RuntimeError):
    """Raised when an approval transition is attempted from a terminal state."""
