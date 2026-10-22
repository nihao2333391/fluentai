"""Repository-level exceptions mapped to HTTP responses by the API."""


class RepositoryNotFoundError(LookupError):
    """Requested resource does not exist."""


class RepositoryConflictError(ValueError):
    """Requested write conflicts with an existing resource."""
