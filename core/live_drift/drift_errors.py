class LiveDriftInputMissingError(Exception):
    """Raised when a required baseline or snapshot file is missing from disk."""
    pass

class InvalidBaselineError(Exception):
    """Raised when a baseline file is malformed, has invalid data, or unsupported schema."""
    pass

class InvalidSnapshotError(Exception):
    """Raised when a snapshot file is malformed, has invalid data, or unsupported schema."""
    pass
