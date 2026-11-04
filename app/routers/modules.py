"""Entry point for the resource module. Real endpoints arrive in step 3.

It exists now so module gating is wired and tested from day one.
The roster module lives in app/modules/roster/.
"""

from fastapi import APIRouter, Depends

from app.deps import require_module
from app.models import Module

resource_router = APIRouter(
    prefix="/api/resources", tags=["Resources"], dependencies=[Depends(require_module(Module.RESOURCE))]
)


@resource_router.get("/status")
def resource_status():
    return {"module": Module.RESOURCE, "enabled": True}
