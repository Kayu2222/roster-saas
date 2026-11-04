from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.db import Base, engine
from app.routers import auth, modules, tenant, users


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Step 1 creates tables directly. Step 4 (PostgreSQL on Azure) switches to Alembic migrations.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Multi-tenant roster & resource management. Companies sign up and choose their modules.",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(tenant.router)
app.include_router(users.router)
app.include_router(modules.roster_router)
app.include_router(modules.resource_router)


@app.get("/health", tags=["Ops"])
def health():
    return {"status": "ok"}
