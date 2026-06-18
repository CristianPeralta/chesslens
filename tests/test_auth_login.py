"""Tests for POST /auth/login (Task 4.2).

Strict TDD: written BEFORE implementation exists.
"""
from __future__ import annotations

from datetime import datetime, timezone

import jwt
import pytest
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
def registered_user(app_client):
    """Register a user and return (email, password, chess_username)."""
    email = "alice@example.com"
    password = "secret123"
    chess_username = "alice"
    resp = app_client.post(
        "/auth/register",
        json={"email": email, "password": password, "chess_username": chess_username},
    )
    assert resp.status_code == 201
    return email, password, chess_username


# ---------------------------------------------------------------------------
# Task 4.2 — POST /auth/login
# ---------------------------------------------------------------------------


class TestLogin:
    def test_login_happy_path_returns_200_with_tokens(self, app_client, registered_user):
        """S-02: successful login returns 200 with access_token, refresh_token."""
        email, password, _ = registered_user
        response = app_client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    def test_login_access_token_has_expected_claims(self, app_client, registered_user):
        """S-02: access_token decodes with chess_username, type=access."""
        email, password, chess_username = registered_user
        response = app_client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        token = response.json()["access_token"]
        payload = jwt.decode(token, "test-secret-long-enough", algorithms=["HS256"])
        assert payload["chess_username"] == chess_username
        assert payload["type"] == "access"

    def test_login_refresh_token_has_expected_claims(self, app_client, registered_user):
        """S-02: refresh_token decodes with type=refresh, no chess_username."""
        email, password, _ = registered_user
        response = app_client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        token = response.json()["refresh_token"]
        payload = jwt.decode(token, "test-secret-long-enough", algorithms=["HS256"])
        assert payload["type"] == "refresh"
        assert "chess_username" not in payload

    def test_login_wrong_password_returns_401(self, app_client, registered_user):
        """S-06: wrong password returns 401 with generic message."""
        email, _, _ = registered_user
        response = app_client.post(
            "/auth/login",
            json={"email": email, "password": "WRONGPASSWORD"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    def test_login_unknown_email_returns_401(self, app_client):
        """S-06: unknown email returns 401 with generic message."""
        response = app_client.post(
            "/auth/login",
            json={"email": "ghost@example.com", "password": "anypassword"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    def test_login_unknown_email_identical_response_to_wrong_password(
        self, app_client, registered_user
    ):
        """S-06: unknown email and wrong password produce identical status+body."""
        email, _, _ = registered_user
        wrong_pw = app_client.post(
            "/auth/login",
            json={"email": email, "password": "WRONGPASSWORD"},
        )
        unknown = app_client.post(
            "/auth/login",
            json={"email": "ghost@example.com", "password": "anypassword"},
        )
        assert wrong_pw.status_code == unknown.status_code
        assert wrong_pw.json() == unknown.json()
