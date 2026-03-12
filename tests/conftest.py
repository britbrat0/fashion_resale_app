"""
Shared pytest fixtures for the ratadat backend test suite.

All tests run against a temporary in-memory SQLite DB and a temporary users CSV
so the real data at /app/data/ is never touched.
"""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

# ── Path setup (must happen before any app imports) ──────────────────────────
# When running locally, add the backend directory to sys.path.
# When running inside Docker (/app/tests), the app module is already importable.
_backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if os.path.isdir(_backend_path):
    sys.path.insert(0, _backend_path)

# Provide stub env vars so pydantic-settings doesn't fail on missing secrets
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-do-not-use-in-production")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("EBAY_APP_ID", "test-ebay-app-id")
os.environ.setdefault("EBAY_CERT_ID", "test-ebay-cert-id")
os.environ.setdefault("ETSY_API_KEY", "test-etsy-api-key")


# ── Low-level DB / file fixtures ─────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path):
    """Return path to a freshly initialised temporary SQLite DB."""
    db_path = str(tmp_path / "test.db")
    with patch("app.database.DB_PATH", db_path):
        from app.database import init_db
        init_db()
    return db_path


@pytest.fixture()
def tmp_users(tmp_path):
    """Return path to an empty users CSV file."""
    users_path = str(tmp_path / "users.csv")
    with open(users_path, "w") as fh:
        fh.write("email,hashed_password,created_at\n")
    return users_path


# ── TestClient fixtures ───────────────────────────────────────────────────────

def _make_patches(tmp_db_path, tmp_users_path):
    """Return list of patch objects that redirect all I/O to temp files."""
    return [
        patch("app.database.DB_PATH", tmp_db_path),
        patch("app.config.settings.db_path", tmp_db_path),
        patch("app.config.settings.users_csv_path", tmp_users_path),
        patch("app.scheduler.jobs.start_scheduler", return_value=None),
        patch("app.scheduler.jobs.stop_scheduler", return_value=None),
        patch("app.scrapers.discovery.load_seed_keywords", return_value=None),
        patch("app.scrapers.discovery.backfill_scale_classifications", return_value=None),
    ]


@pytest.fixture()
def client(tmp_db, tmp_users):
    """
    FastAPI TestClient with:
    - Temporary DB and users CSV
    - Scheduler disabled
    - Auth dependency overridden (always returns 'testuser@example.com')
    """
    patches = _make_patches(tmp_db, tmp_users)
    for p in patches:
        p.start()

    from fastapi.testclient import TestClient
    from app.main import app
    from app.auth.service import get_current_user

    app.dependency_overrides[get_current_user] = lambda: "testuser@example.com"

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()
    for p in reversed(patches):
        p.stop()


@pytest.fixture()
def raw_client(tmp_db, tmp_users):
    """
    FastAPI TestClient WITHOUT an auth override — used specifically for
    testing the register / login flow with real JWT tokens.
    """
    patches = _make_patches(tmp_db, tmp_users)
    for p in patches:
        p.start()

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    for p in reversed(patches):
        p.stop()


# ── Convenience helpers ───────────────────────────────────────────────────────

@pytest.fixture()
def registered_user(raw_client):
    """Register a test user and return (client, email, password)."""
    email, password = "fixture@example.com", "Passw0rd!"
    raw_client.post("/api/auth/register", json={"email": email, "password": password})
    return raw_client, email, password


@pytest.fixture()
def auth_headers(registered_user):
    """Return Authorization headers for the fixture test user."""
    c, email, password = registered_user
    resp = c.post("/api/auth/login", json={"email": email, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def db_rows(tmp_db_path, query, params=()):
    """Helper: run a SELECT against the temp DB and return all rows."""
    with patch("app.database.DB_PATH", tmp_db_path):
        from app.database import get_connection
        conn = get_connection()
        rows = conn.execute(query, params).fetchall()
        conn.close()
    return rows
