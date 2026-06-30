"""Tests for POST /auth/refresh (Task 4.3).

Strict TDD: written BEFORE implementation exists.
NOTE: /auth/* routes removed — JWT auth replaced by cookie-based username.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

pytestmark = pytest.mark.skip(reason="JWT auth routes removed — replaced by cookie-based auth")
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine():
    from chesslens.db.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def app_client(db_engine, monkeypatch):
    import chesslens.db.session as session_module
    from unittest.mock import patch

    test_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(session_module, "SessionLocal", test_factory)
    monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "test-secret-long-enough")
    monkeypatch.setattr("chesslens.delivery.security.settings.access_token_ttl_minutes", 15)
    monkeypatch.setattr("chesslens.delivery.security.settings.refresh_token_ttl_days", 7)

    from chesslens.delivery.api import app

    with patch("chesslens.delivery.api.init_db"):
        with TestClient(app) as c:
            yield c


@pytest.fixture()
def auth_tokens(app_client):
    """Register + login, return (access_token, refresh_token)."""
    app_client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "secret123", "chess_username": "alice"},
    )
    resp = app_client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "secret123"},
    )
    body = resp.json()
    return body["access_token"], body["refresh_token"]


# ---------------------------------------------------------------------------
# Task 4.3 — POST /auth/refresh
# ---------------------------------------------------------------------------


class TestRefresh:
    def test_refresh_happy_path_returns_new_tokens(self, app_client, auth_tokens):
        """S-03: valid refresh token returns 200 with new access+refresh."""
        _, refresh_token = auth_tokens
        response = app_client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    def test_refresh_tokens_are_rotated(self, app_client, auth_tokens):
        """S-03: the new refresh_token differs from the original."""
        _, refresh_token = auth_tokens
        response = app_client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        new_refresh = response.json()["refresh_token"]
        # Tokens should differ (rotation observable as different iat/exp)
        assert new_refresh != refresh_token

    def test_refresh_expired_token_returns_401(self, app_client):
        """S-05: expired refresh token returns 401."""
        # Craft an expired refresh token
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "1",
            "type": "refresh",
            "iat": now - timedelta(days=8),
            "exp": now - timedelta(days=1),
        }
        expired = jwt.encode(payload, "test-secret-long-enough", algorithm="HS256")
        response = app_client.post(
            "/auth/refresh",
            json={"refresh_token": expired},
        )
        assert response.status_code == 401

    def test_refresh_access_token_as_refresh_returns_401(self, app_client, auth_tokens):
        """S-11: passing an access token to /auth/refresh returns 401."""
        access_token, _ = auth_tokens
        response = app_client.post(
            "/auth/refresh",
            json={"refresh_token": access_token},
        )
        assert response.status_code == 401
