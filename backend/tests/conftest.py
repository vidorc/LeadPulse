"""Pytest configuration and shared fixtures.

Tests run against a real PostgreSQL database (the models use server-side
defaults, enums, and constraints that SQLite can't faithfully emulate). Point
``TEST_DATABASE_URL`` at a throwaway database; it defaults to the local
docker-compose test instance.

Environment is set BEFORE importing any app module so the settings singleton
and the import-time rate limiter pick up test-safe values. Schema is created
once per session from the ORM metadata; every test starts from truncated
tables for isolation.
"""

from __future__ import annotations

import os

# ---- Test environment (must be set before importing app.*) ----
os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://leadpulse:testpw@localhost:15432/leadpulse_test",
)
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["APP_ENV"] = "development"  # avoid prod fail-fast secret checks
os.environ["JWT_SECRET_KEY"] = "test-only-secret-not-for-production-use"
# Effectively disable rate limiting during functional tests; a dedicated test
# overrides this to exercise the limiter directly.
os.environ["RATE_LIMIT_LOGIN_PER_MINUTE"] = "100000"
os.environ["RATE_LIMIT_INGEST_PER_MINUTE"] = "100000"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.base import Base  # noqa: E402  (aggregates all models)
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Create the full schema once, drop it at the end of the session."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _no_celery(monkeypatch):
    """Stub the async AI task's .delay so lead creation never touches a broker
    (and never makes a paid LLM call) during tests."""
    from app.tasks import lead_tasks

    monkeypatch.setattr(lead_tasks.process_lead_ai, "delay", lambda *a, **k: None)
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate every table before each test for isolation."""
    table_names = ", ".join(
        f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables)
    )
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def db():
    """A session for service-level tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    """A TestClient with app lifespan (startup/shutdown) handled."""
    with TestClient(app) as c:
        yield c


# ---- Auth helpers ----

_PW = "Sup3r$ecret!"


def _signup(client: TestClient, email: str, org_name: str) -> dict:
    r = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": _PW, "org_name": org_name, "full_name": "T"},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def org_a(client):
    """A signed-up org with an OWNER token. Returns (headers, tokens)."""
    tokens = _signup(client, "owner@acme.co", "Acme")
    return {"Authorization": f"Bearer {tokens['access_token']}"}, tokens


@pytest.fixture
def org_b(client):
    """A second, isolated org for tenancy tests."""
    tokens = _signup(client, "owner@beta.co", "Beta")
    return {"Authorization": f"Bearer {tokens['access_token']}"}, tokens


@pytest.fixture
def auth_headers(org_a):
    headers, _ = org_a
    return headers


def make_lead(client, headers, *, name="Jane", email="jane@buyer.co") -> int:
    r = client.post(
        "/api/v1/leads/",
        headers=headers,
        json={"name": name, "email": email, "source": "manual"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]
