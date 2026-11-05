"""Test setup.

By default every test gets a fresh in-memory SQLite database (fast, no setup).

Set TEST_DATABASE_URL to a throwaway PostgreSQL database to run the same tests
against the real production schema, built by the Alembic migrations, e.g.
    TEST_DATABASE_URL=postgresql+psycopg://roster:roster@localhost:5432/roster_test
CI runs the suite both ways. WARNING: the PostgreSQL database is wiped.
"""

import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
ON_POSTGRES = bool(TEST_DATABASE_URL)


@pytest.fixture(scope="session")
def pg_engine():
    """PostgreSQL only: wipe the database once, then build it with the real migrations."""
    if not ON_POSTGRES:
        yield None
        return
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        cfg = Config("alembic.ini")
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(pg_engine):
    """A clean database for every test."""
    if pg_engine is not None:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        with pg_engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {tables} CASCADE"))
        yield sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
        return

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def register(client, company: str, email: str, modules=("roster",), password="Passw0rd!") -> str:
    res = client.post(
        "/api/auth/register",
        json={
            "company_name": company,
            "owner_name": f"{company} Owner",
            "email": email,
            "password": password,
            "modules": list(modules),
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
