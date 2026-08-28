class Ra2ExplorerError(Exception):
    """Base error for failures that can be shown to a local user."""


class InvalidFormatError(Ra2ExplorerError):
    """Raised when binary input violates the declared format contract."""


class UnsupportedFormatError(Ra2ExplorerError):
    """Raised when an otherwise valid feature is not implemented."""


class AssetNotFoundError(Ra2ExplorerError):
    """Raised when a persisted source or asset no longer exists."""
