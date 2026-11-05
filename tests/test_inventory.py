import pytest

from app.core.errors import DomainError
from app.core.tenancy import set_tenant
from app.models import Role, Tenant, User
from app.modules.inventory import service
from app.modules.inventory.models import Product
from app.modules.inventory.schemas import UseIn
from tests.conftest import auth, register

PW = "Passw0rd!"


@pytest.fixture()
def pharmacy(client):
    owner = auth(register(client, "Clinic", "o@clinic.com", modules=["inventory"]))
    client.post("/api/users", headers=owner, json={"email": "n@clinic.com", "name": "Nurse", "password": PW})
    nurse = auth(client.post("/api/auth/login", json={"email": "n@clinic.com", "password": PW}).json()["access_token"])
    gloves = client.post("/api/inventory/products", headers=owner,
                         json={"name": "Gloves", "unit": "box", "reorder_level": 5, "opening_stock": 10}).json()
    return {"owner": owner, "nurse": nurse, "gloves": gloves}


def _post(client, h, product, action, **body):
    return client.post(f"/api/inventory/products/{product['id']}/{action}", headers=h, json=body)


def test_opening_stock_is_recorded_in_the_ledger(client, pharmacy):
    assert pharmacy["gloves"]["on_hand"] == 10
    ledger = client.get(f"/api/inventory/movements?product_id={pharmacy['gloves']['id']}", headers=pharmacy["owner"]).json()
    assert [(m["reason"], m["change"], m["balance_after"]) for m in ledger] == [("received", 10, 10)]


def test_receive_use_and_ledger_explain_the_number(client, pharmacy):
    g, owner, nurse = pharmacy["gloves"], pharmacy["owner"], pharmacy["nurse"]
    assert _post(client, owner, g, "receive", quantity=5, note="Delivery").json()["on_hand"] == 15
    assert _post(client, nurse, g, "use", quantity=4).json()["on_hand"] == 11

    ledger = client.get(f"/api/inventory/movements?product_id={g['id']}", headers=owner).json()
    assert [m["change"] for m in ledger] == [-4, 5, 10]          # newest first
    assert ledger[0]["balance_after"] == 11
    assert sum(m["change"] for m in ledger) == 11                # the ledger adds up to on_hand


def test_cannot_use_more_than_is_on_hand(client, pharmacy):
    res = _post(client, pharmacy["nurse"], pharmacy["gloves"], "use", quantity=11)
    assert res.status_code == 409
    assert "Only 10 box of Gloves left" in res.json()["detail"]
    assert client.get("/api/inventory/products", headers=pharmacy["owner"]).json()[0]["on_hand"] == 10


def test_low_stock_flag_and_filter(client, pharmacy):
    _post(client, pharmacy["nurse"], pharmacy["gloves"], "use", quantity=5)  # 5 left, reorder level 5
    low = client.get("/api/inventory/products?low_only=true", headers=pharmacy["owner"]).json()
    assert [p["name"] for p in low] == ["Gloves"] and low[0]["low_stock"] is True


def test_stocktake_corrects_and_records_difference(client, pharmacy):
    g = pharmacy["gloves"]
    res = _post(client, pharmacy["owner"], g, "count", counted=8, expected=10, note="Monthly count")
    assert res.json()["on_hand"] == 8
    latest = client.get(f"/api/inventory/movements?product_id={g['id']}", headers=pharmacy["owner"]).json()[0]
    assert (latest["reason"], latest["change"], latest["balance_after"]) == ("counted", -2, 8)


def test_stocktake_rejected_if_stock_moved_meanwhile(client, pharmacy):
    g = pharmacy["gloves"]
    _post(client, pharmacy["nurse"], g, "use", quantity=1)               # 9 now; owner still thinks 10
    res = _post(client, pharmacy["owner"], g, "count", counted=8, expected=10)
    assert res.status_code == 409 and "Count again" in res.json()["detail"]


def test_staff_can_use_but_not_receive_count_or_create(client, pharmacy):
    g, nurse = pharmacy["gloves"], pharmacy["nurse"]
    assert _post(client, nurse, g, "receive", quantity=1).status_code == 403
    assert _post(client, nurse, g, "count", counted=1, expected=10).status_code == 403
    assert client.post("/api/inventory/products", headers=nurse, json={"name": "Masks"}).status_code == 403


def test_staff_see_only_their_own_ledger_entries(client, pharmacy):
    g = pharmacy["gloves"]
    _post(client, pharmacy["nurse"], g, "use", quantity=1)
    mine = client.get("/api/inventory/movements", headers=pharmacy["nurse"]).json()
    assert [m["change"] for m in mine] == [-1]   # not the owner's opening stock


def test_product_names_unique_per_company(client, pharmacy):
    res = client.post("/api/inventory/products", headers=pharmacy["owner"], json={"name": "Gloves"})
    assert res.status_code == 409


def test_inventory_is_isolated_and_gated(client, pharmacy):
    other = auth(register(client, "Other", "o@other.com", modules=["inventory"]))
    assert client.get("/api/inventory/products", headers=other).json() == []
    assert _post(client, other, pharmacy["gloves"], "use", quantity=1).status_code == 404
    assert _post(client, other, pharmacy["gloves"], "receive", quantity=100).status_code == 404

    roster_only = auth(register(client, "Roster", "o@roster.com", modules=["roster"]))
    assert client.get("/api/inventory/products", headers=roster_only).status_code == 403


def test_two_people_taking_the_last_box_at_once(session_factory):
    """Both requests see 1 box. The atomic, guarded UPDATE lets exactly one succeed."""
    setup = session_factory()
    tenant = Tenant(name="Race Co", inventory_enabled=True)
    setup.add(tenant)
    setup.flush()
    set_tenant(setup, tenant.id)
    user = User(email="u@race.com", name="U", password_hash="h", role=Role.STAFF)
    product = Product(name="Last box", unit="box", on_hand=1)
    setup.add_all([user, product])
    setup.commit()
    tid, uid, pid = tenant.id, user.id, product.id
    setup.close()

    s1, s2 = session_factory(), session_factory()
    for s in (s1, s2):
        set_tenant(s, tid)
        assert s.get(Product, pid).on_hand == 1        # both read "1 left"

    service.use(s1, pid, UseIn(quantity=1), created_by=uid)
    with pytest.raises(DomainError) as exc:
        service.use(s2, pid, UseIn(quantity=1), created_by=uid)
    assert exc.value.status_code == 409

    check = session_factory()
    set_tenant(check, tid)
    assert check.get(Product, pid).on_hand == 0
    assert len(service.movements(check, product_id=pid)) == 1
    for s in (s1, s2, check):
        s.close()


def test_database_refuses_negative_stock_directly(session_factory):
    """Even code that skips the service can't push stock below zero (CHECK constraint)."""
    from sqlalchemy.exc import IntegrityError

    db = session_factory()
    tenant = Tenant(name="Check Co", inventory_enabled=True)
    db.add(tenant)
    db.flush()
    set_tenant(db, tenant.id)
    db.add(Product(name="X", on_hand=-1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.close()
