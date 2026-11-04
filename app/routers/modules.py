"""Entry points for the two modules. Real endpoints arrive in step 2 (roster) and step 3 (resource).

They exist now so module gating is wired and tested from day one.
"""

from fastapi import APIRouter, Depends

from app.deps import require_module
from app.models import Module

roster_router = APIRouter(
    prefix="/api/roster", tags=["Roster"], dependencies=[Depends(require_module(Module.ROSTER))]
)
resource_router = APIRouter(
    prefix="/api/resources", tags=["Resources"], dependencies=[Depends(require_module(Module.RESOURCE))]
)


@roster_router.get("/status")
def roster_status():
    return {"module": Module.ROSTER, "enabled": True}


@resource_router.get("/status")
def resource_status():
    return {"module": Module.RESOURCE, "enabled": True}
