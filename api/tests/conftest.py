from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.seed import DEMO_PASSWORD, seed

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock(NOW)


@pytest.fixture
def client(tmp_path, clock):
    settings = Settings(env="dev", database_url=f"sqlite:///{tmp_path / 'test.db'}",
                        jwt_secret="test-secret-at-least-32-bytes-long-000", jwt_minutes=60)
    app = create_app(settings, clock=clock)
    with app.state.session_factory() as db:
        ids = seed(db, NOW)
    c = TestClient(app)
    c.ids = ids
    return c


def login(client, email):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
