class CertificationInputMissingError(Exception):
    """Raised when a required upstream artifact for certification is missing."""
    pass

class CertificationValidationError(Exception):
    """Raised when a loaded upstream artifact is malformed, mismatched, or incompatible."""
    pass
