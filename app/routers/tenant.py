from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_tenant, get_current_user, require_roles
from app.models import Role, Tenant, User
from app.schemas import MeOut, TenantOut, UpdateModulesRequest, UserOut

router = APIRouter(prefix="/api", tags=["Company"])


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user), tenant: Tenant = Depends(get_current_tenant)):
    return MeOut(user=UserOut.model_validate(user), tenant=TenantOut.model_validate(tenant))


@router.get("/tenant", response_model=TenantOut)
def get_tenant(tenant: Tenant = Depends(get_current_tenant)):
    return tenant


@router.put("/tenant/modules", response_model=TenantOut)
def update_modules(
    body: UpdateModulesRequest,
    _: User = Depends(require_roles(Role.OWNER)),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Owner switches modules on or off. Data is kept when a module is switched off."""
    tenant.set_modules(body.modules)
    db.commit()
    return tenant
