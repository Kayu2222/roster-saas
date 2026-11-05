"""One error type for broken business rules, shared by every module.

Services raise DomainError(status_code, message); a single handler in main.py
turns it into a JSON response. Services never import FastAPI.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError


class DomainError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def is_overlap_violation(exc: IntegrityError) -> bool:
    """True when PostgreSQL refused a row because of an exclusion constraint (SQLSTATE 23P01).

    That is the database-level backstop for overlapping shifts and bookings
    (see migrations/versions/0002_overlap_constraints.py).
    """
    return getattr(exc.orig, "sqlstate", None) == "23P01"


async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})
