"""Brute-force protection for sign-in.

Too many failed sign-ins for one email address within a short window lock that email
for a while; during the lock even the right password is refused (429 + Retry-After).

Design choices:
- Counted per EMAIL, whether or not an account exists. Unknown emails are counted and
  locked exactly like real ones, so the lockout never reveals which emails are registered.
- Stored in the database, not in memory: it survives restarts and holds across replicas.
- The row is read with SELECT ... FOR UPDATE on PostgreSQL, so parallel guesses can't
  slip past the limit by all reading the same old count.
- A successful sign-in clears the record.

Trade-off: anyone who knows an email can lock it for a few minutes. That is the usual price
of account lockout; per-IP limits at the edge are the next layer for real production traffic.
"""

import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import LoginThrottle


def utcnow() -> datetime:
    """Current time; tests replace this to move the clock."""
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    # SQLite hands timestamps back without a timezone; they were stored as UTC.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _seconds_until(moment: datetime | None, now: datetime) -> int:
    if moment is None:
        return 0
    return max(0, math.ceil((_aware(moment) - now).total_seconds()))


def seconds_locked(db: Session, email: str) -> int:
    """How many seconds this email stays locked (0 = not locked)."""
    row = db.get(LoginThrottle, email)
    return _seconds_until(row.locked_until, utcnow()) if row else 0


def _locked_row(db: Session, email: str) -> LoginThrottle | None:
    return db.scalar(select(LoginThrottle).where(LoginThrottle.email == email).with_for_update())


def record_failure(db: Session, email: str) -> int:
    """Count one failed sign-in. Returns the lock length in seconds if this failure locked the email, else 0."""
    now = utcnow()
    row = _locked_row(db, email)
    if row is None:
        db.add(LoginThrottle(email=email, failures=0, window_started_at=now))
        try:
            db.flush()
        except IntegrityError:  # another request created it at the same moment
            db.rollback()
        row = _locked_row(db, email)

    window_over = _aware(row.window_started_at) <= now - timedelta(minutes=settings.login_window_minutes)
    lock_over = row.locked_until is not None and _seconds_until(row.locked_until, now) == 0
    if window_over or lock_over:
        row.failures, row.window_started_at, row.locked_until = 0, now, None

    row.failures += 1
    locked_for = 0
    if row.failures >= settings.login_max_failures:
        row.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
        locked_for = settings.login_lockout_minutes * 60
    db.commit()
    return locked_for


def clear(db: Session, email: str) -> None:
    """Forget past failures after a successful sign-in."""
    db.execute(delete(LoginThrottle).where(LoginThrottle.email == email))
    db.commit()
