"""Web fixtures for test modules that do not define their own `app`."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from shoponline.config import Settings
from shoponline.web.app import create_app
from shoponline.web.auth import set_user
from tests.sap_setup import NO_ENV


@pytest.fixture
def app(db, tmp_path):
    settings = Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data")
    set_user(db, "admin", "admin-password", "admin")
    set_user(db, "viewer", "viewer-password", "viewer")
    return create_app(
        settings,
        session_factory=lambda: Session(
            bind=db.bind, join_transaction_mode="create_savepoint", expire_on_commit=False
        ),
        env=NO_ENV,
    )


@pytest.fixture
def login(app):
    """login("admin") / login("viewer"): a client signed in with that test account."""

    def _login(username: str) -> TestClient:
        client = TestClient(app)
        resp = client.post(
            "/login",
            data={"username": username, "password": f"{username}-password"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        return client

    return _login
