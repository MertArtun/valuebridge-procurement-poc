class ApprovalRequiredError(RuntimeError):
    """Raised when a write action is attempted without explicit approval."""
