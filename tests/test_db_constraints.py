"""PostgreSQL-only: the database itself refuses overlaps, even if the application check is skipped.

This simulates two requests that both passed the application's overlap check at the
same instant. Runs only when TEST_DATABASE_URL points at PostgreSQL (CI does this).
"""

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import DomainError
from app.core.tenancy import set_tenant
from app.models import Role, Tenant, User
from app.modules.resources.models import Booking, BookingStatus, Resource, ResourceType
from app.modules.roster import service as roster_service
from app.modules.roster.models import Shift
from app.modules.roster.schemas import ShiftIn
from tests.conftest import ON_POSTGRES

pytestmark = pytest.mark.skipif(not ON_POSTGRES, reason="needs PostgreSQL (set TEST_DATABASE_URL)")

T9, T13, T17 = datetime(2026, 11, 10, 9), datetime(2026, 11, 10, 13), datetime(2026, 11, 10, 17)


@pytest.fixture()
def world(session_factory):
    db = session_factory()
    tenant = Tenant(name="Constraint Co", roster_enabled=True, resource_enabled=True)
    db.add(tenant)
    db.flush()
    set_tenant(db, tenant.id)
    user = User(email="c@c.com", name="Casey", password_hash="h", role=Role.MANAGER)
    rtype = ResourceType(name="Room")
    db.add_all([user, rtype])
    db.flush()
    room = Resource(resource_type_id=rtype.id, name="Room 1")
    db.add(room)
    db.commit()
    yield db, user, room
    db.close()


def test_db_refuses_overlapping_shifts(world):
    db, user, _ = world
    db.add(Shift(user_id=user.id, start_at=T9, end_at=T17, created_by=user.id))
    db.commit()
    db.add(Shift(user_id=user.id, start_at=T13, end_at=datetime(2026, 11, 10, 20), created_by=user.id))
    with pytest.raises(IntegrityError) as exc:
        db.commit()
    assert exc.value.orig.sqlstate == "23P01"  # exclusion_violation
    db.rollback()


def test_db_allows_back_to_back_shifts(world):
    db, user, _ = world
    db.add(Shift(user_id=user.id, start_at=T9, end_at=T13, created_by=user.id))
    db.add(Shift(user_id=user.id, start_at=T13, end_at=T17, created_by=user.id))
    db.commit()


def test_db_refuses_shift_ending_before_start(world):
    db, user, _ = world
    db.add(Shift(user_id=user.id, start_at=T17, end_at=T9, created_by=user.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_race_on_shifts_becomes_a_clean_409(world, monkeypatch):
    """The app check is bypassed (as if both requests passed it at once); the user still gets 409, not 500."""
    db, user, _ = world
    db.add(Shift(user_id=user.id, start_at=T9, end_at=T17, created_by=user.id))
    db.commit()

    monkeypatch.setattr(roster_service, "find_clash", lambda *a, **k: None)
    body = ShiftIn(user_id=user.id, start_at=T13, end_at=datetime(2026, 11, 10, 20))
    with pytest.raises(DomainError) as exc:
        roster_service.create_shift(db, body, created_by=user.id)
    assert exc.value.status_code == 409


def test_db_refuses_overlapping_active_bookings_but_ignores_cancelled(world):
    db, user, room = world
    db.add(Booking(resource_id=room.id, start_at=T9, end_at=T13, booked_by=user.id,
                   status=BookingStatus.CANCELLED))
    db.add(Booking(resource_id=room.id, start_at=T9, end_at=T13, booked_by=user.id))
    db.commit()  # a cancelled booking does not block the slot

    db.add(Booking(resource_id=room.id, start_at=datetime(2026, 11, 10, 12), end_at=T17, booked_by=user.id))
    with pytest.raises(IntegrityError) as exc:
        db.commit()
    assert exc.value.orig.sqlstate == "23P01"
    db.rollback()
