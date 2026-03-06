"""
Tests for user authentication:
  - POST /api/auth/register
  - POST /api/auth/login
  - Service-layer unit tests (token generation, password hashing)
  - Protected route access with/without a valid token
"""

import pytest
from unittest.mock import patch


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegister:
    def test_register_new_user_returns_token(self, raw_client):
        resp = raw_client.post(
            "/api/auth/register",
            json={"email": "alice@example.com", "password": "securepass123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 20

    def test_register_duplicate_email_returns_400(self, raw_client):
        payload = {"email": "bob@example.com", "password": "pass123"}
        raw_client.post("/api/auth/register", json=payload)
        resp = raw_client.post("/api/auth/register", json=payload)
        assert resp.status_code == 400
        assert "already" in resp.json()["detail"].lower()

    def test_register_creates_usable_account(self, raw_client):
        """Registering then logging in with the same credentials must succeed."""
        raw_client.post(
            "/api/auth/register",
            json={"email": "carol@example.com", "password": "mypass"},
        )
        login_resp = raw_client.post(
            "/api/auth/login",
            json={"email": "carol@example.com", "password": "mypass"},
        )
        assert login_resp.status_code == 200


# ── Login ─────────────────────────────────────────────────────────────────────

class TestLogin:
    def test_login_valid_credentials_returns_token(self, registered_user):
        c, email, password = registered_user
        resp = c.post("/api/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_wrong_password_returns_401(self, registered_user):
        c, email, _ = registered_user
        resp = c.post(
            "/api/auth/login",
            json={"email": email, "password": "totally_wrong"},
        )
        assert resp.status_code == 401

    def test_login_unknown_email_returns_401(self, raw_client):
        resp = raw_client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "pass"},
        )
        assert resp.status_code == 401

    def test_login_returns_bearer_token_type(self, registered_user):
        c, email, password = registered_user
        resp = c.post("/api/auth/login", json={"email": email, "password": password})
        assert resp.json()["token_type"] == "bearer"


# ── JWT token structure ───────────────────────────────────────────────────────

class TestJWT:
    def test_token_is_decodable_jwt(self, registered_user):
        """The issued token must decode to a payload containing the user's email."""
        from jose import jwt as jose_jwt
        from app.config import settings

        c, email, password = registered_user
        resp = c.post("/api/auth/login", json={"email": email, "password": password})
        token = resp.json()["access_token"]

        payload = jose_jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        assert payload["sub"] == email

    def test_token_contains_expiry(self, registered_user):
        from jose import jwt as jose_jwt
        from app.config import settings

        c, email, password = registered_user
        resp = c.post("/api/auth/login", json={"email": email, "password": password})
        token = resp.json()["access_token"]
        payload = jose_jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        assert "exp" in payload


# ── Auth service unit tests ───────────────────────────────────────────────────

class TestAuthService:
    def test_password_hashing_and_verification(self, tmp_users):
        with patch("app.config.settings.users_csv_path", tmp_users):
            from app.auth.service import hash_password, verify_password
            hashed = hash_password("mysecretpassword")
            assert hashed != "mysecretpassword"
            assert verify_password("mysecretpassword", hashed) is True
            assert verify_password("wrongpassword", hashed) is False

    def test_create_token_returns_string(self, tmp_users):
        with patch("app.config.settings.users_csv_path", tmp_users):
            from app.auth.service import create_token
            token = create_token("user@example.com")
            assert isinstance(token, str)
            assert len(token) > 10

    def test_register_and_login_service_functions(self, tmp_users):
        with patch("app.config.settings.users_csv_path", tmp_users):
            from app.auth.service import register_user, login_user
            token = register_user("svc@example.com", "pass123")
            assert isinstance(token, str)
            login_token = login_user("svc@example.com", "pass123")
            assert isinstance(login_token, str)


# ── Protected route access ────────────────────────────────────────────────────

class TestProtectedRoutes:
    def test_protected_route_without_token_is_rejected(self, raw_client):
        """Accessing a protected endpoint with no Authorization header → 403."""
        resp = raw_client.get("/api/trends/keywords/list")
        assert resp.status_code == 403

    def test_protected_route_with_invalid_token_is_rejected(self, raw_client):
        resp = raw_client.get(
            "/api/trends/keywords/list",
            headers={"Authorization": "Bearer this.is.not.valid"},
        )
        assert resp.status_code == 401

    def test_protected_route_with_valid_token_succeeds(self, registered_user, auth_headers):
        c, _, _ = registered_user
        resp = c.get("/api/trends/keywords/list", headers=auth_headers)
        assert resp.status_code == 200

    def test_chat_history_requires_auth(self, raw_client):
        resp = raw_client.get("/api/chat/history")
        assert resp.status_code == 403

    def test_vintage_eras_requires_auth(self, raw_client):
        resp = raw_client.get("/api/vintage/eras")
        assert resp.status_code == 403
