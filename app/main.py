from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.db import Base, engine
from app.modules.roster import models as _roster_models  # noqa: F401  (registers tables)
from app.modules.roster.router import roster_error_handler
from app.modules.roster.router import router as roster_router
from app.modules.roster.service import RosterError
from app.routers import auth, modules, tenant, users


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Creates missing tables. Step 4 (PostgreSQL on Azure) switches to Alembic migrations.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="Multi-tenant roster & resource management. Companies sign up and choose their modules.",
    lifespan=lifespan,
)

app.add_exception_handler(RosterError, roster_error_handler)

app.include_router(auth.router)
app.include_router(tenant.router)
app.include_router(users.router)
app.include_router(roster_router)
app.include_router(modules.resource_router)


@app.get("/health", tags=["Ops"])
def health():
    return {"status": "ok"}
