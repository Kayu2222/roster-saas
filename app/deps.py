"""Request-level dependencies: who is calling, which company, what they may do."""

import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.core.tenancy import set_tenant
from app.db import get_db
from app.models import Module, Role, Tenant, User

bearer = HTTPBearer(auto_error=False)

_unauthorized = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing token",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise _unauthorized
    try:
        payload = decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
        tenant_id = uuid.UUID(payload["tid"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _unauthorized

    # From here on, every query in this request is limited to this company.
    set_tenant(db, tenant_id)

    user = db.get(User, user_id)
    if user is None or not user.is_active or user.tenant_id != tenant_id:
        raise _unauthorized
    return user


def get_current_tenant(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Tenant:
    return db.get(Tenant, user.tenant_id)


def require_roles(*roles: Role) -> Callable[..., User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot do this")
        return user

    return checker


def require_module(module: Module) -> Callable[..., Tenant]:
    """Blocks the endpoint unless the caller's company has this module switched on."""

    def checker(tenant: Tenant = Depends(get_current_tenant)) -> Tenant:
        if not tenant.has_module(module):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"The '{module.value}' module is not enabled for your company")
        return tenant

    return checker
