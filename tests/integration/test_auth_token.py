"""Tests for API token minting and CLI commands."""

import datetime
import os
import subprocess
import sys

import jwt
import pytest

from server.auth import create_api_token, verify_app_token
from server.config import JWT_SECRET


# ---------------------------------------------------------------------------
# TestCreateApiToken
# ---------------------------------------------------------------------------

class TestCreateApiToken:
    def test_token_has_correct_claims(self):
        token = create_api_token(email="test@example.com", name="Test User")
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], issuer="cycling-coach")
        assert claims["email"] == "test@example.com"
        assert claims["name"] == "Test User"
        assert claims["type"] == "api"
        assert claims["iss"] == "cycling-coach"
        assert claims["picture"] == ""

    def test_custom_expiry(self):
        token = create_api_token(email="test@example.com", expiry_days=7)
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], issuer="cycling-coach")
        exp = datetime.datetime.fromtimestamp(claims["exp"], tz=datetime.timezone.utc)
        iat = datetime.datetime.fromtimestamp(claims["iat"], tz=datetime.timezone.utc)
        delta = exp - iat
        assert delta.days == 7

    def test_default_expiry_is_365_days(self):
        token = create_api_token(email="test@example.com")
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], issuer="cycling-coach")
        exp = datetime.datetime.fromtimestamp(claims["exp"], tz=datetime.timezone.utc)
        iat = datetime.datetime.fromtimestamp(claims["iat"], tz=datetime.timezone.utc)
        delta = exp - iat
        assert delta.days == 365

    def test_verify_app_token_accepts_api_token(self):
        token = create_api_token(email="test@example.com", name="Test User")
        claims = verify_app_token(token)
        assert claims["email"] == "test@example.com"
        assert claims["type"] == "api"

    def test_expired_token_rejected(self):
        token = create_api_token(email="test@example.com", expiry_days=-1)
        with pytest.raises(Exception):
            verify_app_token(token)


# ---------------------------------------------------------------------------
# TestApiTokenWithEndpoints
# ---------------------------------------------------------------------------

class TestApiTokenWithEndpoints:
    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient
        from server.main import app
        return TestClient(app)

    def test_api_token_accesses_protected_endpoint(self, client):
        """API token works as a Bearer token on protected endpoints (auth disabled in tests)."""
        token = create_api_token(email="dev@localhost", name="Dev User")
        resp = client.get("/api/rides?limit=1", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_missing_token_still_works_when_auth_disabled(self, client):
        """With GOOGLE_AUTH_ENABLED=false, endpoints are accessible without a token."""
        resp = client.get("/api/rides?limit=1")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestMintTokenCLI
# ---------------------------------------------------------------------------

class TestMintTokenCLI:
    def test_mint_token_user_not_found(self):
        result = subprocess.run(
            [sys.executable, "-m", "server", "mint-token", "--email", "nonexistent@example.com"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "No user" in result.stderr

    def test_mint_token_no_jwt_secret(self):
        env = os.environ.copy()
        env["JWT_SECRET"] = ""
        result = subprocess.run(
            [sys.executable, "-m", "server", "mint-token", "--email", "test@example.com"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode != 0
        assert "JWT_SECRET" in result.stderr
