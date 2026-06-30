"""Tests for POST /auth/register (Task 4.1).

Strict TDD: written BEFORE delivery/auth.py exists.
NOTE: /auth/* routes removed — JWT auth replaced by cookie-based username.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skip(reason="JWT auth routes removed — replaced by cookie-based auth")
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine():
    """In-memory SQLite with all tables.

    WHY StaticPool + check_same_thread=False: TestClient runs routes in a
    separate thread; StaticPool forces all connections to share the same
    in-memory database so seeded rows are visible inside route handlers.
    """
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
    """TestClient wired to in-memory DB with JWT secret set."""
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


# ---------------------------------------------------------------------------
# Task 4.1 — POST /auth/register
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_happy_path_returns_201(self, app_client):
        """S-01: successful registration returns 201."""
        response = app_client.post(
            "/auth/register",
            json={
                "email": "alice@example.com",
                "password": "secret123",
                "chess_username": "alice",
            },
        )
        assert response.status_code == 201

    def test_register_response_has_no_password_field(self, app_client):
        """S-01: response must not contain password or password_hash."""
        response = app_client.post(
            "/auth/register",
            json={
                "email": "alice@example.com",
                "password": "secret123",
                "chess_username": "alice",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert "password" not in body
        assert "password_hash" not in body

    def test_register_response_contains_user_fields(self, app_client):
        """S-01: response contains id, email, chess_username, created_at."""
        response = app_client.post(
            "/auth/register",
            json={
                "email": "alice@example.com",
                "password": "secret123",
                "chess_username": "alice",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert "id" in body
        assert body["email"] == "alice@example.com"
        assert body["chess_username"] == "alice"
        assert "created_at" in body

    def test_register_duplicate_email_returns_409(self, app_client):
        """S-07: duplicate registration by email returns 409."""
        payload = {
            "email": "alice@example.com",
            "password": "secret123",
            "chess_username": "alice",
        }
        app_client.post("/auth/register", json=payload)
        response = app_client.post(
            "/auth/register",
            json={"email": "alice@example.com", "password": "different9", "chess_username": "alice2"},
        )
        assert response.status_code == 409

    def test_register_duplicate_email_does_not_create_second_user(self, app_client, db_engine):
        """S-07: DB row count stays 1 after duplicate registration attempt."""
        from chesslens.db.models import UserRow

        payload = {
            "email": "alice@example.com",
            "password": "secret123",
            "chess_username": "alice",
        }
        app_client.post("/auth/register", json=payload)
        app_client.post(
            "/auth/register",
            json={"email": "alice@example.com", "password": "different9", "chess_username": "alice2"},
        )
        with Session(bind=db_engine) as s:
            count = s.query(UserRow).filter_by(email="alice@example.com").count()
        assert count == 1

    def test_register_password_too_short_returns_422(self, app_client):
        """S-15: password shorter than 8 chars returns 422."""
        response = app_client.post(
            "/auth/register",
            json={"email": "bob@example.com", "password": "short", "chess_username": "bob"},
        )
        assert response.status_code == 422

    def test_register_password_too_short_creates_no_db_row(self, app_client, db_engine):
        """S-15: no UserRow created when password is too short."""
        from chesslens.db.models import UserRow

        app_client.post(
            "/auth/register",
            json={"email": "bob@example.com", "password": "short", "chess_username": "bob"},
        )
        with Session(bind=db_engine) as s:
            count = s.query(UserRow).filter_by(email="bob@example.com").count()
        assert count == 0
