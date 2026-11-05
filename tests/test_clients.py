from tests.conftest import auth, register

PW = "Passw0rd!"


def _client(client, h, name="Jamie Lee", **extra):
    res = client.post("/api/clients", headers=h, json={"name": name, **extra})
    assert res.status_code == 201, res.text
    return res.json()


def test_add_search_and_update(client):
    h = auth(register(client, "Clinic", "o@clinic.com"))
    _client(client, h, "Jamie Lee", phone="0400 111 222")
    _client(client, h, "Sam Park", email="sam@example.com")

    assert [c["name"] for c in client.get("/api/clients?q=jam", headers=h).json()] == ["Jamie Lee"]
    assert [c["name"] for c in client.get("/api/clients?q=example.com", headers=h).json()] == ["Sam Park"]
    assert [c["name"] for c in client.get("/api/clients?q=0400", headers=h).json()] == ["Jamie Lee"]

    sam = client.get("/api/clients?q=sam", headers=h).json()[0]
    res = client.patch(f"/api/clients/{sam['id']}", headers=h, json={"phone": "0499 000 000"})
    assert res.json()["phone"] == "0499 000 000"


def test_archived_clients_are_hidden_but_kept(client):
    h = auth(register(client, "Clinic", "o@clinic.com"))
    c = _client(client, h)
    assert client.patch(f"/api/clients/{c['id']}", headers=h, json={"is_active": False}).status_code == 200
    assert client.get("/api/clients", headers=h).json() == []
    assert len(client.get("/api/clients?include_archived=true", headers=h).json()) == 1


def test_staff_can_add_clients_but_not_archive(client):
    owner = auth(register(client, "Clinic", "o@clinic.com"))
    client.post("/api/users", headers=owner, json={"email": "rec@clinic.com", "name": "Reception", "password": PW})
    staff = auth(client.post("/api/auth/login", json={"email": "rec@clinic.com", "password": PW}).json()["access_token"])
    c = _client(client, staff, "Walk-in")
    assert client.patch(f"/api/clients/{c['id']}", headers=staff, json={"is_active": False}).status_code == 403


def test_clients_are_isolated(client):
    a = auth(register(client, "Company A", "o@a.com"))
    b = auth(register(client, "Company B", "o@b.com"))
    c = _client(client, a)
    assert client.get("/api/clients", headers=b).json() == []
    assert client.get(f"/api/clients/{c['id']}", headers=b).status_code == 404
    assert client.patch(f"/api/clients/{c['id']}", headers=b, json={"name": "Hacked"}).status_code == 404


def test_booking_for_a_client_shows_in_their_activity(client):
    h = auth(register(client, "Clinic", "o@clinic.com", modules=["resource", "inventory"]))
    rtype = client.post("/api/resources/types", headers=h, json={"name": "Bed"}).json()["id"]
    bed = client.post("/api/resources", headers=h, json={"resource_type_id": rtype, "name": "Bed 3A"}).json()["id"]
    patient = _client(client, h, "Jamie Lee")

    res = client.post("/api/resources/bookings", headers=h, json={
        "resource_id": bed, "start_at": "2026-11-10T08:00", "end_at": "2026-11-12T10:00", "client_id": patient["id"]})
    assert res.status_code == 201 and res.json()["client_id"] == patient["id"]

    product = client.post("/api/inventory/products", headers=h, json={"name": "Paracetamol", "unit": "tablet", "opening_stock": 20}).json()
    client.post(f"/api/inventory/products/{product['id']}/use", headers=h, json={"quantity": 2, "client_id": patient["id"]})

    activity = client.get(f"/api/clients/{patient['id']}/activity", headers=h).json()
    assert {a["kind"] for a in activity} == {"booking", "usage"}
    assert any(a["title"] == "Bed 3A" for a in activity)
    assert any(a["title"] == "Paracetamol" and a["detail"].startswith("2 tablet") for a in activity)


def test_cannot_book_for_another_companys_client(client):
    a = auth(register(client, "Company A", "o@a.com", modules=["resource"]))
    b = auth(register(client, "Company B", "o@b.com", modules=["resource"]))
    rtype = client.post("/api/resources/types", headers=b, json={"name": "Room"}).json()["id"]
    room = client.post("/api/resources", headers=b, json={"resource_type_id": rtype, "name": "Room 1"}).json()["id"]
    foreign = _client(client, a)
    res = client.post("/api/resources/bookings", headers=b, json={
        "resource_id": room, "start_at": "2026-11-10T08:00", "end_at": "2026-11-10T09:00", "client_id": foreign["id"]})
    assert res.status_code == 404
