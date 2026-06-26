class RegistryError(Exception):
    """Base exception for all strategy registry errors."""

    pass


class DuplicateStrategyIdError(RegistryError):
    """Raised when attempting to load a strategy with an ID that already exists in the registry."""

    pass


class MissingMetadataError(RegistryError):
    """Raised when a strategy manifest is missing required metadata."""

    pass


class InvalidLifecycleStateError(RegistryError):
    """Raised when a strategy specifies an invalid lifecycle state."""

    pass


class LoaderDiscoveryError(RegistryError):
    """Raised when there is an error discovering strategies."""

    pass
