import pytest

from tests.conftest import auth, register

PW = "Passw0rd!"


@pytest.fixture()
def acme(client):
    """A company with an owner, a nurse and a barista-only staff member."""
    owner = register(client, "Acme Clinic", "owner@acme.com", modules=["roster"])
    h = auth(owner)

    def new_user(email, name):
        res = client.post("/api/users", headers=h, json={"email": email, "name": name, "password": PW})
        assert res.status_code == 201, res.text
        return res.json()["id"]

    def new_role(name):
        res = client.post("/api/roster/job-roles", headers=h, json={"name": name})
        assert res.status_code == 201, res.text
        return res.json()["id"]

    nurse_role, barista_role = new_role("Nurse"), new_role("Barista")
    nina, ben = new_user("nina@acme.com", "Nina"), new_user("ben@acme.com", "Ben")
    client.put(f"/api/roster/staff/{nina}/job-roles", headers=h, json={"job_role_ids": [nurse_role]})
    client.put(f"/api/roster/staff/{ben}/job-roles", headers=h, json={"job_role_ids": [barista_role]})

    return {"h": h, "nina": nina, "ben": ben, "nurse_role": nurse_role, "barista_role": barista_role}


def _shift(client, h, **body):
    return client.post("/api/roster/shifts", headers=h, json=body)


def _shift_type(client, h, name, start, end, job_role_id=None):
    res = client.post("/api/roster/shift-types", headers=h,
                      json={"name": name, "start_time": start, "end_time": end, "job_role_id": job_role_id})
    assert res.status_code == 201, res.text
    return res.json()


# ---------- job roles & shift types ----------

def test_job_role_names_unique_per_company(client, acme):
    res = client.post("/api/roster/job-roles", headers=acme["h"], json={"name": "Nurse"})
    assert res.status_code == 409
    # ...but another company can use the same name
    other = register(client, "Other Co", "o@other.com", modules=["roster"])
    assert client.post("/api/roster/job-roles", headers=auth(other), json={"name": "Nurse"}).status_code == 201


def test_staff_qualifications_roundtrip(client, acme):
    roles = client.get(f"/api/roster/staff/{acme['nina']}/job-roles", headers=acme["h"]).json()
    assert [r["name"] for r in roles] == ["Nurse"]


def test_overnight_shift_type(client, acme):
    night = _shift_type(client, acme["h"], "Night", "22:00", "06:00")
    assert night["overnight"] is True
    res = _shift(client, acme["h"], user_id=acme["nina"], shift_type_id=night["id"], date="2026-11-10")
    assert res.status_code == 201
    assert res.json()["start_at"] == "2026-11-10T22:00:00"
    assert res.json()["end_at"] == "2026-11-11T06:00:00"


# ---------- shift rules ----------

def test_create_shift_with_exact_times(client, acme):
    res = _shift(client, acme["h"], user_id=acme["nina"], start_at="2026-11-10T09:00", end_at="2026-11-10T17:00")
    assert res.status_code == 201


def test_double_booking_rejected(client, acme):
    h, nina = acme["h"], acme["nina"]
    assert _shift(client, h, user_id=nina, start_at="2026-11-10T09:00", end_at="2026-11-10T17:00").status_code == 201
    clash = _shift(client, h, user_id=nina, start_at="2026-11-10T16:00", end_at="2026-11-10T20:00")
    assert clash.status_code == 409
    assert "already has a shift" in clash.json()["detail"]


def test_back_to_back_shifts_allowed(client, acme):
    h, nina = acme["h"], acme["nina"]
    assert _shift(client, h, user_id=nina, start_at="2026-11-10T09:00", end_at="2026-11-10T13:00").status_code == 201
    assert _shift(client, h, user_id=nina, start_at="2026-11-10T13:00", end_at="2026-11-10T17:00").status_code == 201


def test_unqualified_staff_rejected(client, acme):
    nurse_shift = _shift_type(client, acme["h"], "Ward AM", "07:00", "15:00", job_role_id=acme["nurse_role"])
    ok = _shift(client, acme["h"], user_id=acme["nina"], shift_type_id=nurse_shift["id"], date="2026-11-10")
    bad = _shift(client, acme["h"], user_id=acme["ben"], shift_type_id=nurse_shift["id"], date="2026-11-10")
    assert ok.status_code == 201
    assert bad.status_code == 409
    assert "not qualified" in bad.json()["detail"]


@pytest.mark.parametrize("start,end", [
    ("2026-11-10T17:00", "2026-11-10T09:00"),   # ends before it starts
    ("2026-11-10T00:00", "2026-11-11T08:00"),   # 32 hours
])
def test_invalid_times_rejected(client, acme, start, end):
    assert _shift(client, acme["h"], user_id=acme["nina"], start_at=start, end_at=end).status_code == 422


def test_must_choose_one_way_to_give_times(client, acme):
    st = _shift_type(client, acme["h"], "AM", "07:00", "15:00")
    both = _shift(client, acme["h"], user_id=acme["nina"], shift_type_id=st["id"], date="2026-11-10",
                  start_at="2026-11-10T07:00", end_at="2026-11-10T15:00")
    neither = _shift(client, acme["h"], user_id=acme["nina"])
    assert both.status_code == neither.status_code == 422


def test_cannot_delete_job_role_in_use(client, acme):
    _shift_type(client, acme["h"], "Ward AM", "07:00", "15:00", job_role_id=acme["nurse_role"])
    res = client.delete(f"/api/roster/job-roles/{acme['nurse_role']}", headers=acme["h"])
    assert res.status_code == 409


# ---------- who sees what ----------

def test_staff_only_see_their_own_shifts(client, acme):
    h = acme["h"]
    _shift(client, h, user_id=acme["nina"], start_at="2026-11-10T09:00", end_at="2026-11-10T17:00")
    _shift(client, h, user_id=acme["ben"], start_at="2026-11-10T09:00", end_at="2026-11-10T17:00")

    manager_view = client.get("/api/roster/shifts?from=2026-11-09&to=2026-11-15", headers=h).json()
    assert len(manager_view) == 2

    ben = client.post("/api/auth/login", json={"email": "ben@acme.com", "password": PW}).json()["access_token"]
    # Even asking for Nina's shifts explicitly, Ben only gets his own.
    ben_view = client.get(f"/api/roster/shifts?from=2026-11-09&to=2026-11-15&user_id={acme['nina']}",
                          headers=auth(ben)).json()
    assert [s["user_id"] for s in ben_view] == [acme["ben"]]


def test_staff_cannot_create_shifts(client, acme):
    ben = client.post("/api/auth/login", json={"email": "ben@acme.com", "password": PW}).json()["access_token"]
    res = _shift(client, auth(ben), user_id=acme["ben"], start_at="2026-11-10T09:00", end_at="2026-11-10T17:00")
    assert res.status_code == 403


def test_list_includes_shift_overlapping_range_edge(client, acme):
    night = _shift_type(client, acme["h"], "Night", "22:00", "06:00")
    _shift(client, acme["h"], user_id=acme["nina"], shift_type_id=night["id"], date="2026-11-08")
    # Shift runs Sun 22:00 to Mon 06:00, so it shows up when listing from Monday.
    shifts = client.get("/api/roster/shifts?from=2026-11-09&to=2026-11-09", headers=acme["h"]).json()
    assert len(shifts) == 1


def test_range_limit(client, acme):
    res = client.get("/api/roster/shifts?from=2026-01-01&to=2026-12-31", headers=acme["h"])
    assert res.status_code == 422


# ---------- isolation ----------

def test_cannot_roster_someone_from_another_company(client, acme):
    other = register(client, "Other Co", "o@other.com", modules=["roster"])
    res = _shift(client, auth(other), user_id=acme["nina"], start_at="2026-11-10T09:00", end_at="2026-11-10T17:00")
    assert res.status_code == 404


def test_cannot_use_another_companys_job_role(client, acme):
    other = register(client, "Other Co", "o@other.com", modules=["roster"])
    res = client.post("/api/roster/shift-types", headers=auth(other),
                      json={"name": "X", "start_time": "07:00", "end_time": "15:00", "job_role_id": acme["nurse_role"]})
    assert res.status_code == 404


def test_shift_lists_are_isolated(client, acme):
    _shift(client, acme["h"], user_id=acme["nina"], start_at="2026-11-10T09:00", end_at="2026-11-10T17:00")
    other = register(client, "Other Co", "o@other.com", modules=["roster"])
    assert client.get("/api/roster/shifts?from=2026-11-09&to=2026-11-15", headers=auth(other)).json() == []
