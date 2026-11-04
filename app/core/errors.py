"""One error type for broken business rules, shared by every module.

Services raise DomainError(status_code, message); a single handler in main.py
turns it into a JSON response. Services never import FastAPI.
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})
