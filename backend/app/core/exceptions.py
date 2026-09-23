"""
Domain exceptions.
Services raise these — never raw HTTPException — so business logic stays
transport-agnostic (the same service could back a REST route, a WebSocket
handler, or a Celery task). The FastAPI exception handlers registered in
main.py translate these into the right HTTP status + JSON body.
"""


class DomainError(Exception):
    """Base class for all domain-level errors."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(DomainError):
    """Raised when a requested entity does not exist (→ HTTP 404)."""


class UnauthorizedError(DomainError):
    """Raised on invalid/expired credentials (→ HTTP 401)."""


class ForbiddenError(DomainError):
    """Raised when an authenticated actor lacks permission (→ HTTP 403)."""


class ConflictError(DomainError):
    """Raised on uniqueness/state conflicts, e.g. duplicate email (→ HTTP 409)."""


class ValidationError(DomainError):
    """Raised on business-rule validation failures (→ HTTP 422)."""
