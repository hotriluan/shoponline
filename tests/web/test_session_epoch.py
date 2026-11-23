"""A restore raises ops.system_state.session_epoch: sessions from before it are logged out.
Each request also notes when the user was last seen (at most once a minute)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from shoponline.db.models import AppUser


def _bump(db):
    db.execute(text("UPDATE ops.system_state SET session_epoch = session_epoch + 1"))


def test_session_is_valid_until_the_epoch_changes(app, login, db):
    client = login("admin")
    assert client.get("/batches", follow_redirects=False).status_code == 200
    _bump(db)
    resp = client.get("/batches", follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/login"
    # The session was cleared, so the old cookie does not come back to life.
    assert client.get("/batches", follow_redirects=False).status_code == 303


def test_login_after_the_restore_works(app, login, db):
    _bump(db)
    client = login("viewer")
    assert client.get("/batches", follow_redirects=False).status_code == 200


def test_session_without_epoch_counts_as_epoch_zero(app, login, db):
    """Sessions made before epochs existed keep working until the first restore."""
    db.execute(text("UPDATE ops.system_state SET session_epoch = 0"))
    client = login("admin")
    assert client.get("/batches", follow_redirects=False).status_code == 200


def test_last_seen_is_noted_at_most_once_a_minute(app, login, db):
    client = login("admin")
    client.get("/batches")
    user = db.scalar(select(AppUser).where(AppUser.username == "admin"))
    first = user.last_seen_at
    assert first is not None and datetime.now(UTC) - first < timedelta(minutes=1)
    client.get("/batches")
    db.refresh(user)
    assert user.last_seen_at == first
    user.last_seen_at = first - timedelta(minutes=5)
    db.flush()
    client.get("/batches")
    db.refresh(user)
    assert user.last_seen_at > first - timedelta(minutes=5)
