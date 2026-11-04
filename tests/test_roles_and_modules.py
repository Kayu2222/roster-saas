from tests.conftest import auth, register


def _login(client, email):
    return client.post("/api/auth/login", json={"email": email, "password": "Passw0rd!"}).json()["access_token"]


def _create(client, token, email, role):
    return client.post("/api/users", headers=auth(token),
                       json={"email": email, "name": email, "password": "Passw0rd!", "role": role})


# ---------- roles ----------

def test_staff_cannot_add_users(client):
    owner = register(client, "Acme", "owner@acme.com")
    assert _create(client, owner, "s@acme.com", "staff").status_code == 201
    staff = _login(client, "s@acme.com")
    assert _create(client, staff, "s2@acme.com", "staff").status_code == 403


def test_only_owner_can_add_managers(client):
    owner = register(client, "Acme", "owner@acme.com")
    assert _create(client, owner, "m@acme.com", "manager").status_code == 201
    manager = _login(client, "m@acme.com")
    assert _create(client, manager, "s@acme.com", "staff").status_code == 201
    assert _create(client, manager, "m2@acme.com", "manager").status_code == 403


def test_nobody_can_create_a_second_owner(client):
    owner = register(client, "Acme", "owner@acme.com")
    assert _create(client, owner, "o2@acme.com", "owner").status_code == 400


# ---------- modules ----------

def test_module_gating(client):
    token = register(client, "Roster Only Co", "owner@r.com", modules=["roster"])
    assert client.get("/api/roster/job-roles", headers=auth(token)).status_code == 200
    assert client.get("/api/resources/types", headers=auth(token)).status_code == 403


def test_owner_can_switch_modules(client):
    token = register(client, "Acme", "owner@acme.com", modules=["roster"])
    res = client.put("/api/tenant/modules", headers=auth(token), json={"modules": ["resource"]})
    assert res.status_code == 200
    assert res.json()["modules"] == ["resource"]
    assert client.get("/api/roster/job-roles", headers=auth(token)).status_code == 403
    assert client.get("/api/resources/types", headers=auth(token)).status_code == 200


def test_non_owner_cannot_switch_modules(client):
    owner = register(client, "Acme", "owner@acme.com")
    _create(client, owner, "m@acme.com", "manager")
    manager = _login(client, "m@acme.com")
    res = client.put("/api/tenant/modules", headers=auth(manager), json={"modules": ["resource"]})
    assert res.status_code == 403
