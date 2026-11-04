from tests.conftest import auth, register


def test_register_then_me(client):
    token = register(client, "Acme Clinic", "owner@acme.com", modules=["roster", "resource"])
    body = client.get("/api/me", headers=auth(token)).json()
    assert body["user"]["role"] == "owner"
    assert body["tenant"]["name"] == "Acme Clinic"
    assert set(body["tenant"]["modules"]) == {"roster", "resource"}


def test_login_works_and_email_is_case_insensitive(client):
    register(client, "Acme", "Owner@Acme.com")
    res = client.post("/api/auth/login", json={"email": "owner@acme.com", "password": "Passw0rd!"})
    assert res.status_code == 200
    assert res.json()["access_token"]


def test_wrong_password_and_unknown_email_look_the_same(client):
    register(client, "Acme", "owner@acme.com")
    wrong_pw = client.post("/api/auth/login", json={"email": "owner@acme.com", "password": "nope-nope"})
    no_user = client.post("/api/auth/login", json={"email": "ghost@acme.com", "password": "nope-nope"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_duplicate_email_rejected(client):
    register(client, "Acme", "owner@acme.com")
    res = client.post(
        "/api/auth/register",
        json={"company_name": "Other", "owner_name": "X", "email": "owner@acme.com",
              "password": "Passw0rd!", "modules": ["roster"]},
    )
    assert res.status_code == 409


def test_must_pick_at_least_one_module(client):
    res = client.post(
        "/api/auth/register",
        json={"company_name": "Acme", "owner_name": "X", "email": "a@acme.com", "password": "Passw0rd!", "modules": []},
    )
    assert res.status_code == 422


def test_requests_without_or_with_bad_token_are_rejected(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers=auth("not-a-jwt")).status_code == 401


def test_password_hash_never_returned(client):
    token = register(client, "Acme", "owner@acme.com")
    for path in ["/api/me", "/api/users"]:
        assert "password" not in client.get(path, headers=auth(token)).text
