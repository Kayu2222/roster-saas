from datetime import datetime

import pytest

from app.core.errors import DomainError
from app.core.tenancy import set_tenant
from app.models import Role, Tenant, User
from app.modules.resources import service
from app.modules.resources.models import Booking, Resource, ResourceType
from app.modules.resources.schemas import BookingIn
from tests.conftest import auth, register

PW = "Passw0rd!"


@pytest.fixture()
def office(client):
    """A company with two meeting rooms, a van, and one staff member."""
    owner = register(client, "Acme Office", "owner@acme.com", modules=["resource"])
    h = auth(owner)

    room_type = client.post("/api/resources/types", headers=h, json={"name": "Meeting room"}).json()["id"]
    van_type = client.post("/api/resources/types", headers=h, json={"name": "Van"}).json()["id"]

    def new_resource(type_id, name):
        res = client.post("/api/resources", headers=h, json={"resource_type_id": type_id, "name": name})
        assert res.status_code == 201, res.text
        return res.json()

    room_a, room_b = new_resource(room_type, "Room A"), new_resource(room_type, "Room B")
    van = new_resource(van_type, "Van 1")

    client.post("/api/users", headers=h, json={"email": "sam@acme.com", "name": "Sam", "password": PW})
    sam = client.post("/api/auth/login", json={"email": "sam@acme.com", "password": PW}).json()["access_token"]

    return {"h": h, "sam": auth(sam), "room_type": room_type, "room_a": room_a, "room_b": room_b, "van": van}


def _book(client, h, resource_id, start, end, purpose=None):
    return client.post("/api/resources/bookings", headers=h,
                       json={"resource_id": resource_id, "start_at": start, "end_at": end, "purpose": purpose})


# ---------- setup ----------

def test_resource_names_unique_per_company(client, office):
    res = client.post("/api/resources", headers=office["h"],
                      json={"resource_type_id": office["room_type"], "name": "Room A"})
    assert res.status_code == 409


def test_staff_cannot_create_resources(client, office):
    res = client.post("/api/resources", headers=office["sam"],
                      json={"resource_type_id": office["room_type"], "name": "Room C"})
    assert res.status_code == 403


def test_cannot_delete_type_that_has_resources(client, office):
    assert client.delete(f"/api/resources/types/{office['room_type']}", headers=office["h"]).status_code == 409


def test_list_resources_by_type(client, office):
    rooms = client.get(f"/api/resources?type_id={office['room_type']}", headers=office["h"]).json()
    assert [r["name"] for r in rooms] == ["Room A", "Room B"]


# ---------- booking rules ----------

def test_staff_can_book(client, office):
    res = _book(client, office["sam"], office["room_a"]["id"], "2026-11-10T14:00", "2026-11-10T15:00", "Standup")
    assert res.status_code == 201


def test_overlapping_booking_rejected(client, office):
    room = office["room_a"]["id"]
    assert _book(client, office["h"], room, "2026-11-10T14:00", "2026-11-10T15:00").status_code == 201
    clash = _book(client, office["sam"], room, "2026-11-10T14:30", "2026-11-10T16:00")
    assert clash.status_code == 409
    assert "already booked" in clash.json()["detail"]


def test_back_to_back_bookings_allowed(client, office):
    room = office["room_a"]["id"]
    assert _book(client, office["h"], room, "2026-11-10T14:00", "2026-11-10T15:00").status_code == 201
    assert _book(client, office["h"], room, "2026-11-10T15:00", "2026-11-10T16:00").status_code == 201


def test_same_time_different_resource_allowed(client, office):
    assert _book(client, office["h"], office["room_a"]["id"], "2026-11-10T14:00", "2026-11-10T15:00").status_code == 201
    assert _book(client, office["h"], office["room_b"]["id"], "2026-11-10T14:00", "2026-11-10T15:00").status_code == 201


def test_multi_day_booking(client, office):
    res = _book(client, office["h"], office["van"]["id"], "2026-11-10T08:00", "2026-11-13T18:00", "Site visit")
    assert res.status_code == 201


@pytest.mark.parametrize("start,end", [
    ("2026-11-10T15:00", "2026-11-10T14:00"),   # ends before it starts
    ("2026-01-01T00:00", "2026-06-01T00:00"),   # longer than 90 days
])
def test_invalid_booking_times(client, office, start, end):
    assert _book(client, office["h"], office["room_a"]["id"], start, end).status_code == 422


def test_out_of_service_resource_cannot_be_booked(client, office):
    van = office["van"]
    res = client.patch(f"/api/resources/{van['id']}", headers=office["h"],
                       json={"version": van["version"], "status": "out_of_service"})
    assert res.status_code == 200
    assert _book(client, office["h"], van["id"], "2026-11-10T08:00", "2026-11-10T12:00").status_code == 409


# ---------- cancelling ----------

def test_cancel_frees_the_slot_and_keeps_history(client, office):
    room = office["room_a"]["id"]
    booking = _book(client, office["sam"], room, "2026-11-10T14:00", "2026-11-10T15:00").json()
    assert client.post(f"/api/resources/bookings/{booking['id']}/cancel", headers=office["sam"]).status_code == 200
    assert _book(client, office["h"], room, "2026-11-10T14:00", "2026-11-10T15:00").status_code == 201

    q = "/api/resources/bookings?from=2026-11-10&to=2026-11-10"
    assert len(client.get(q, headers=office["h"]).json()) == 1
    assert len(client.get(q + "&include_cancelled=true", headers=office["h"]).json()) == 2


def test_staff_cannot_cancel_someone_elses_booking(client, office):
    booking = _book(client, office["h"], office["room_a"]["id"], "2026-11-10T14:00", "2026-11-10T15:00").json()
    res = client.post(f"/api/resources/bookings/{booking['id']}/cancel", headers=office["sam"])
    assert res.status_code == 403


def test_staff_only_see_own_bookings(client, office):
    _book(client, office["h"], office["room_a"]["id"], "2026-11-10T09:00", "2026-11-10T10:00", "Board meeting")
    _book(client, office["sam"], office["room_b"]["id"], "2026-11-10T09:00", "2026-11-10T10:00", "1:1")
    q = "/api/resources/bookings?from=2026-11-10&to=2026-11-10"
    assert len(client.get(q, headers=office["h"]).json()) == 2
    assert [b["purpose"] for b in client.get(q, headers=office["sam"]).json()] == ["1:1"]


# ---------- availability ----------

def test_availability_search(client, office):
    _book(client, office["h"], office["room_a"]["id"], "2026-11-10T14:00", "2026-11-10T15:00")
    q = f"/api/resources/availability?start_at=2026-11-10T14:30&end_at=2026-11-10T15:30&type_id={office['room_type']}"
    free = client.get(q, headers=office["sam"]).json()
    assert [r["name"] for r in free] == ["Room B"]


# ---------- optimistic locking ----------

def test_edit_with_stale_version_is_rejected(client, office):
    room = office["room_a"]
    first = client.patch(f"/api/resources/{room['id']}", headers=office["h"],
                         json={"version": room["version"], "location": "Level 2"})
    assert first.status_code == 200
    assert first.json()["version"] == room["version"] + 1

    # A second editor still holding the old copy tries to save.
    stale = client.patch(f"/api/resources/{room['id']}", headers=office["h"],
                         json={"version": room["version"], "location": "Level 3"})
    assert stale.status_code == 409


def test_simultaneous_bookings_cannot_both_win(session_factory):
    """Two requests read the same free slot at the same moment. Only one booking may be created."""
    setup = session_factory()
    tenant = Tenant(name="Race Co", resource_enabled=True)
    setup.add(tenant)
    setup.flush()
    set_tenant(setup, tenant.id)
    user = User(email="u@race.com", name="U", password_hash="h", role=Role.MANAGER)
    rtype = ResourceType(name="Room")
    setup.add_all([user, rtype])
    setup.flush()
    room = Resource(resource_type_id=rtype.id, name="Room 1")
    setup.add(room)
    setup.commit()
    ids = (tenant.id, user.id, room.id)
    setup.close()

    body = BookingIn(resource_id=ids[2], start_at=datetime(2026, 11, 10, 14), end_at=datetime(2026, 11, 10, 15))

    # Both sessions load the resource and see no overlapping booking...
    s1, s2 = session_factory(), session_factory()
    loaded = {}
    for s in (s1, s2):
        set_tenant(s, ids[0])
        loaded[s] = s.get(Resource, ids[2])  # both hold version 1
        assert service.find_overlap(s, ids[2], body.start_at, body.end_at) is None

    # ...the first one commits...
    service.create_booking(s1, body, booked_by=ids[1])
    # ...and the second one is stopped by the version check, not by the overlap check it already passed.
    s2.add(Booking(resource_id=ids[2], start_at=body.start_at, end_at=body.end_at, booked_by=ids[1]))
    loaded[s2].updated_at = datetime.now()  # still the version-1 copy it read earlier
    with pytest.raises(DomainError) as exc:
        service._commit_or_conflict(s2)
    assert exc.value.status_code == 409

    check = session_factory()
    set_tenant(check, ids[0])
    assert len(service.list_bookings(check, body.start_at.date(), body.start_at.date())) == 1
    for s in (s1, s2, check):
        s.close()


# ---------- isolation ----------

def test_cannot_book_another_companys_resource(client, office):
    other = register(client, "Other Co", "o@other.com", modules=["resource"])
    res = _book(client, auth(other), office["room_a"]["id"], "2026-11-10T14:00", "2026-11-10T15:00")
    assert res.status_code == 404


def test_availability_is_isolated(client, office):
    other = register(client, "Other Co", "o@other.com", modules=["resource"])
    free = client.get("/api/resources/availability?start_at=2026-11-10T14:00&end_at=2026-11-10T15:00",
                      headers=auth(other)).json()
    assert free == []


def test_resource_module_must_be_enabled(client):
    roster_only = register(client, "Roster Co", "r@r.com", modules=["roster"])
    assert client.get("/api/resources", headers=auth(roster_only)).status_code == 403
