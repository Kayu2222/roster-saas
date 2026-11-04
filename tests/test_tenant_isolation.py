"""The most important tests in the project: company A must never see company B's data."""

import pytest
from sqlalchemy import select

from app.core.tenancy import TenantContextMissing, set_tenant
from app.models import Role, Tenant, User
from tests.conftest import auth, register


def _add_staff(client, token, email, name="Staff"):
    res = client.post("/api/users", headers=auth(token),
                      json={"email": email, "name": name, "password": "Passw0rd!", "role": "staff"})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_user_list_only_shows_own_company(client):
    a = register(client, "Company A", "owner@a.com")
    b = register(client, "Company B", "owner@b.com")
    _add_staff(client, a, "alice@a.com")
    _add_staff(client, b, "bob@b.com")

    a_emails = {u["email"] for u in client.get("/api/users", headers=auth(a)).json()}
    b_emails = {u["email"] for u in client.get("/api/users", headers=auth(b)).json()}

    assert a_emails == {"owner@a.com", "alice@a.com"}
    assert b_emails == {"owner@b.com", "bob@b.com"}


def test_cannot_fetch_other_company_user_by_id(client):
    a = register(client, "Company A", "owner@a.com")
    b = register(client, "Company B", "owner@b.com")
    bob_id = _add_staff(client, b, "bob@b.com")

    assert client.get(f"/api/users/{bob_id}", headers=auth(b)).status_code == 200
    # Same id, other company: 404, not 403, so A can't even learn the id exists.
    assert client.get(f"/api/users/{bob_id}", headers=auth(a)).status_code == 404


def test_query_without_tenant_context_fails_loudly(session_factory):
    db = session_factory()
    with pytest.raises(TenantContextMissing):
        db.scalars(select(User)).all()
    db.close()


def test_cannot_save_row_into_another_tenant(session_factory):
    db = session_factory()
    t1, t2 = Tenant(name="T1"), Tenant(name="T2")
    db.add_all([t1, t2])
    db.flush()

    set_tenant(db, t1.id)
    db.add(User(tenant_id=t2.id, email="x@t2.com", name="X", password_hash="h", role=Role.STAFF))
    with pytest.raises(PermissionError):
        db.flush()
    db.close()


def test_new_rows_are_stamped_with_current_tenant(session_factory):
    db = session_factory()
    t1 = Tenant(name="T1")
    db.add(t1)
    db.flush()

    set_tenant(db, t1.id)
    u = User(email="y@t1.com", name="Y", password_hash="h", role=Role.STAFF)  # no tenant_id given
    db.add(u)
    db.flush()
    assert u.tenant_id == t1.id
    db.close()
