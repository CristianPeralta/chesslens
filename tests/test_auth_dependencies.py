"""Tests for auth security primitives (delivery/security.py).

Strict TDD: written BEFORE the implementation.
Covers Tasks 3.1 (password hashing), 3.2 (token creation),
3.3 (decode_token), and 3.4 (get_current_user dependency).
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine():
    """In-memory SQLite engine with all tables (including users).

    WHY StaticPool + check_same_thread=False: TestClient runs routes in a
    separate thread. In-memory SQLite creates a NEW empty database per
    connection by default — StaticPool forces all connections (across threads)
    to share the same in-memory database so the tables seeded in the fixture
    are visible inside route handlers.
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
def db_session_factory(db_engine):
    """Session factory bound to the in-memory engine."""
    return sessionmaker(bind=db_engine, expire_on_commit=False)


@pytest.fixture()
def sample_user(db_engine):
    """A UserRow persisted in the in-memory DB."""
    from chesslens.db.models import UserRow

    user = UserRow(
        email="alice@example.com",
        password_hash="$2b$12$fakehash",
        chess_username="alice_chess",
        created_at=datetime.now(timezone.utc),
    )
    with Session(bind=db_engine) as session:
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


# ---------------------------------------------------------------------------
# Task 3.1 — Password hashing helpers
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    def test_hash_password_returns_bcrypt_hash(self):
        """hash_password returns a bcrypt hash starting with $2b$."""
        from chesslens.delivery.security import hash_password

        hashed = hash_password("mysecretpassword")
        assert hashed.startswith("$2b$")

    def test_verify_password_correct_plain_returns_true(self):
        """verify_password returns True for matching plain/hashed pair."""
        from chesslens.delivery.security import hash_password, verify_password

        plain = "correctpassword"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_verify_password_wrong_plain_returns_false(self):
        """verify_password returns False when the plain text is wrong."""
        from chesslens.delivery.security import hash_password, verify_password

        hashed = hash_password("originalpassword")
        assert verify_password("wrongpassword", hashed) is False


# ---------------------------------------------------------------------------
# Task 3.2 — JWT token creation
# ---------------------------------------------------------------------------


class TestTokenCreation:
    def test_create_access_token_contains_expected_claims(self, sample_user, monkeypatch):
        """create_access_token returns a JWT with sub, chess_username, type=access, exp."""
        monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "testsecret")
        monkeypatch.setattr(
            "chesslens.delivery.security.settings.access_token_ttl_minutes", 15
        )

        from chesslens.delivery.security import create_access_token

        token = create_access_token(sample_user)
        payload = jwt.decode(token, "testsecret", algorithms=["HS256"])

        assert payload["sub"] == str(sample_user.id)
        assert payload["chess_username"] == "alice_chess"
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload
        # exp should be in the future
        assert payload["exp"] > datetime.now(timezone.utc).timestamp()

    def test_create_refresh_token_contains_expected_claims(self, sample_user, monkeypatch):
        """create_refresh_token returns a JWT with sub, type=refresh, exp — no chess_username."""
        monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "testsecret")
        monkeypatch.setattr("chesslens.delivery.security.settings.refresh_token_ttl_days", 7)

        from chesslens.delivery.security import create_refresh_token

        token = create_refresh_token(sample_user)
        payload = jwt.decode(token, "testsecret", algorithms=["HS256"])

        assert payload["sub"] == str(sample_user.id)
        assert payload["type"] == "refresh"
        assert "exp" in payload
        assert "chess_username" not in payload

    def test_create_access_token_raises_when_secret_empty(self, sample_user, monkeypatch):
        """create_access_token raises RuntimeError when jwt_secret is empty."""
        monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "")

        from chesslens.delivery.security import create_access_token

        with pytest.raises(RuntimeError, match="CHESSLENS_JWT_SECRET"):
            create_access_token(sample_user)

    def test_create_refresh_token_raises_when_secret_empty(self, sample_user, monkeypatch):
        """create_refresh_token raises RuntimeError when jwt_secret is empty."""
        monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "")

        from chesslens.delivery.security import create_refresh_token

        with pytest.raises(RuntimeError, match="CHESSLENS_JWT_SECRET"):
            create_refresh_token(sample_user)


# ---------------------------------------------------------------------------
# Task 3.3 — decode_token with type guard
# ---------------------------------------------------------------------------


def _make_token(secret: str, token_type: str, exp_delta: timedelta | None = None) -> str:
    """Helper: craft a raw JWT for testing decode_token."""
    now = datetime.now(timezone.utc)
    exp = now + (exp_delta if exp_delta is not None else timedelta(minutes=15))
    payload = {
        "sub": "1",
        "type": token_type,
        "iat": now,
        "exp": exp,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


class TestDecodeToken:
    def test_decode_token_valid_access(self, monkeypatch):
        """decode_token returns payload for a valid access token."""
        monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "testsecret")

        from chesslens.delivery.security import decode_token

        token = _make_token("testsecret", "access")
        payload = decode_token(token, expected_type="access")
        assert payload["type"] == "access"
        assert payload["sub"] == "1"

    def test_decode_token_expired_raises(self, monkeypatch):
        """decode_token raises jwt.InvalidTokenError for an expired token."""
        monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "testsecret")

        from chesslens.delivery.security import decode_token

        token = _make_token("testsecret", "access", exp_delta=timedelta(seconds=-1))
        with pytest.raises(jwt.exceptions.InvalidTokenError):
            decode_token(token, expected_type="access")

    def test_decode_token_tampered_raises(self, monkeypatch):
        """decode_token raises jwt.InvalidTokenError for a tampered signature."""
        monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "testsecret")

        from chesslens.delivery.security import decode_token

        token = _make_token("testsecret", "access")
        # WHY first char, not last: the last base64url char of a 32-byte HMAC encodes
        # only 4 HMAC bits + 2 padding bits. PyJWT ignores the padding bits, so changing
        # only them leaves the decoded signature unchanged. The first char always encodes
        # 6 full HMAC bits — changing it guarantees an actual signature mismatch.
        parts = token.split(".")
        parts[2] = ("B" if parts[2][0] != "B" else "C") + parts[2][1:]
        tampered = ".".join(parts)

        with pytest.raises(jwt.exceptions.InvalidTokenError):
            decode_token(tampered, expected_type="access")

    def test_decode_token_wrong_type_raises(self, monkeypatch):
        """decode_token raises jwt.InvalidTokenError when type claim mismatches expected_type."""
        monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "testsecret")

        from chesslens.delivery.security import decode_token

        refresh_token = _make_token("testsecret", "refresh")
        with pytest.raises(jwt.exceptions.InvalidTokenError):
            decode_token(refresh_token, expected_type="access")

    def test_decode_token_rejects_none_algorithm(self, monkeypatch):
        """decode_token rejects a token signed with the 'none' algorithm."""
        monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "testsecret")

        from chesslens.delivery.security import decode_token

        # Craft a "none" alg token manually (PyJWT raises on encode with alg=none,
        # so build raw header.payload.empty-signature)
        import base64
        import json

        header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
        now = int(datetime.now(timezone.utc).timestamp())
        body_bytes = json.dumps(
            {"sub": "1", "type": "access", "iat": now, "exp": now + 900}
        ).encode()
        payload_b64 = base64.urlsafe_b64encode(body_bytes).rstrip(b"=").decode()
        none_token = f"{header}.{payload_b64}."

        with pytest.raises(jwt.exceptions.InvalidTokenError):
            decode_token(none_token, expected_type="access")


# ---------------------------------------------------------------------------
# Task 3.4 — get_current_user FastAPI dependency
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_app(db_engine, monkeypatch):
    """A minimal FastAPI app with a protected route and in-memory DB."""
    import chesslens.db.session as session_module
    from chesslens.db.models import UserRow
    from fastapi import FastAPI

    # Patch session factory to use in-memory DB
    test_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(session_module, "SessionLocal", test_factory)
    monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "testsecret")
    monkeypatch.setattr(
        "chesslens.delivery.security.settings.access_token_ttl_minutes", 15
    )
    monkeypatch.setattr("chesslens.delivery.security.settings.refresh_token_ttl_days", 7)

    # Seed a user
    user = UserRow(
        email="dep@example.com",
        password_hash="$2b$12$fakehash",
        chess_username="dep_chess",
        created_at=datetime.now(timezone.utc),
    )
    with Session(bind=db_engine) as s:
        s.add(user)
        s.commit()
        s.refresh(user)

    from chesslens.delivery.security import get_current_user

    app = FastAPI()

    @app.get("/protected")
    def protected(current_user=pytest.importorskip("fastapi").Depends(get_current_user)):
        return {"chess_username": current_user.chess_username}

    return app, user


class TestGetCurrentUser:
    def test_get_current_user_no_token_returns_401(self, test_app):
        """GET /protected with no Authorization header returns 401."""
        app, _ = test_app
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/protected")
        assert response.status_code == 401

    def test_get_current_user_expired_token_returns_401(self, test_app, monkeypatch):
        """GET /protected with an expired access token returns 401."""
        monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "testsecret")
        app, user = test_app
        expired_token = _make_token("testsecret", "access", exp_delta=timedelta(seconds=-1))
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/protected", headers={"Authorization": f"Bearer {expired_token}"})
        assert response.status_code == 401

    def test_get_current_user_tampered_token_returns_401(self, test_app, monkeypatch):
        """GET /protected with a tampered token returns 401."""
        monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "testsecret")
        app, user = test_app
        good_token = _make_token("testsecret", "access")
        parts = good_token.split(".")
        # WHY first char: see test_decode_token_tampered_raises for the base64url padding explanation.
        parts[2] = ("B" if parts[2][0] != "B" else "C") + parts[2][1:]
        tampered = ".".join(parts)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/protected", headers={"Authorization": f"Bearer {tampered}"})
        assert response.status_code == 401

    def test_get_current_user_refresh_token_as_access_returns_401(self, test_app, monkeypatch):
        """GET /protected with a refresh token (wrong type) returns 401."""
        monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "testsecret")
        app, user = test_app
        refresh_token = _make_token("testsecret", "refresh")
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/protected", headers={"Authorization": f"Bearer {refresh_token}"}
        )
        assert response.status_code == 401

    def test_get_current_user_orphan_sub_returns_401(self, test_app, monkeypatch):
        """GET /protected with token sub pointing to nonexistent user returns 401."""
        monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "testsecret")
        app, _ = test_app
        # craft token with nonexistent user_id
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "99999",
            "chess_username": "ghost",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=15),
        }
        orphan_token = jwt.encode(payload, "testsecret", algorithm="HS256")
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/protected", headers={"Authorization": f"Bearer {orphan_token}"}
        )
        assert response.status_code == 401

    def test_get_current_user_valid_token_returns_user(self, test_app, monkeypatch):
        """GET /protected with valid access token returns user data."""
        monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "testsecret")
        monkeypatch.setattr(
            "chesslens.delivery.security.settings.access_token_ttl_minutes", 15
        )
        app, user = test_app

        from chesslens.delivery.security import create_access_token

        token = create_access_token(user)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["chess_username"] == "dep_chess"
