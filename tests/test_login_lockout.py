"""Brute-force protection on sign-in (app/core/login_throttle.py)."""

from datetime import timedelta

import pytest

from app.core import login_throttle
from app.core.config import settings
from tests.conftest import register

MAX = settings.login_max_failures
RIGHT = "Passw0rd!"


def login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def fail(client, email, times):
    return [login(client, email, "wrong-password").status_code for _ in range(times)]


@pytest.fixture()
def clock(monkeypatch):
    """Lets a test move time forward instead of waiting."""
    now = {"t": login_throttle.utcnow()}
    monkeypatch.setattr(login_throttle, "utcnow", lambda: now["t"])

    def advance(minutes):
        now["t"] += timedelta(minutes=minutes)

    return advance


def test_locks_after_too_many_failures_even_with_the_right_password(client, clock):
    register(client, "Acme", "owner@acme.com")
    assert fail(client, "owner@acme.com", MAX) == [401] * (MAX - 1) + [429]

    res = login(client, "owner@acme.com", RIGHT)
    assert res.status_code == 429
    assert int(res.headers["Retry-After"]) == settings.login_lockout_minutes * 60
    assert "Try again in" in res.json()["detail"]


def test_lock_wears_off(client, clock):
    register(client, "Acme", "owner@acme.com")
    fail(client, "owner@acme.com", MAX)
    clock(settings.login_lockout_minutes - 1)
    assert login(client, "owner@acme.com", RIGHT).status_code == 429
    clock(2)
    assert login(client, "owner@acme.com", RIGHT).status_code == 200


def test_unknown_email_is_locked_exactly_like_a_real_one(client, clock):
    """Otherwise the lockout itself would reveal which emails are registered."""
    register(client, "Acme", "owner@acme.com")
    assert fail(client, "owner@acme.com", MAX + 1) == fail(client, "ghost@acme.com", MAX + 1)
    real = login(client, "owner@acme.com", "wrong-password")
    ghost = login(client, "ghost@acme.com", "wrong-password")
    assert real.status_code == ghost.status_code == 429
    assert real.json() == ghost.json()


def test_success_resets_the_count(client, clock):
    register(client, "Acme", "owner@acme.com")
    fail(client, "owner@acme.com", MAX - 1)
    assert login(client, "owner@acme.com", RIGHT).status_code == 200
    assert fail(client, "owner@acme.com", MAX - 1) == [401] * (MAX - 1)


def test_old_failures_drop_out_of_the_window(client, clock):
    register(client, "Acme", "owner@acme.com")
    fail(client, "owner@acme.com", MAX - 1)
    clock(settings.login_window_minutes + 1)
    assert fail(client, "owner@acme.com", MAX - 1) == [401] * (MAX - 1)
    assert login(client, "owner@acme.com", RIGHT).status_code == 200


def test_after_a_lock_the_count_starts_again(client, clock):
    register(client, "Acme", "owner@acme.com")
    fail(client, "owner@acme.com", MAX)
    clock(settings.login_lockout_minutes + 1)
    assert fail(client, "owner@acme.com", 1) == [401]


def test_lockout_is_per_email(client, clock):
    register(client, "Acme", "owner@acme.com")
    register(client, "Beta", "owner@beta.com")
    fail(client, "owner@acme.com", MAX)
    assert login(client, "owner@beta.com", RIGHT).status_code == 200


def test_changing_the_email_case_does_not_get_around_it(client, clock):
    register(client, "Acme", "owner@acme.com")
    fail(client, "Owner@Acme.com", MAX - 1)
    assert fail(client, "OWNER@acme.com", 1) == [429]
