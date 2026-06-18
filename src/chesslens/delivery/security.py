"""Auth security primitives for chesslens.

WHY: Lives in delivery/ — not core/ — to keep the hexagonal boundary clean.
Core has zero knowledge of JWT, bcrypt, or FastAPI.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from chesslens.config import settings
from chesslens.db.models import UserRow
from chesslens.db.session import get_session

# ---------------------------------------------------------------------------
# Password hashing — bcrypt directly (no passlib; passlib breaks on bcrypt>=4)
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if the plaintext matches the bcrypt hash, False otherwise."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# JWT token creation
# ---------------------------------------------------------------------------


def create_access_token(user: UserRow) -> str:
    """Return a signed HS256 JWT access token for the given user.

    Raises RuntimeError if CHESSLENS_JWT_SECRET is empty — never issue tokens
    with an empty secret.
    """
    if not settings.jwt_secret:
        raise RuntimeError("CHESSLENS_JWT_SECRET is not set — cannot issue tokens")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "chess_username": user.chess_username,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token(user: UserRow) -> str:
    """Return a signed HS256 JWT refresh token for the given user.

    Raises RuntimeError if CHESSLENS_JWT_SECRET is empty.
    """
    if not settings.jwt_secret:
        raise RuntimeError("CHESSLENS_JWT_SECRET is not set — cannot issue tokens")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_ttl_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# Token decoding with type guard
# ---------------------------------------------------------------------------


def decode_token(token: str, expected_type: str) -> dict:
    """Decode and validate a JWT, enforcing the expected type claim.

    Raises jwt.exceptions.InvalidTokenError (or a subclass) for:
    - expired tokens
    - tampered / wrong-signature tokens
    - wrong type claim (e.g. refresh token used where access expected)
    - "none" algorithm (PyJWT 2.x rejects this by default via algorithms=[...])
    """
    # WHY algorithms=["HS256"] explicitly: PyJWT 2.x refuses the "none"
    # algorithm when a non-empty algorithms list is provided.
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if payload.get("type") != expected_type:
        raise jwt.exceptions.InvalidTokenError(
            f"Token type '{payload.get('type')}' does not match expected '{expected_type}'"
        )
    return payload


# ---------------------------------------------------------------------------
# FastAPI dependency — get_current_user
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    """Return a uniform 401 HTTPException — no information leakage."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UserRow:
    """FastAPI dependency: decode the Bearer token and return the matching UserRow.

    Returns UserRow on success. Raises HTTP 401 for ALL failure modes:
    missing token, expired, tampered, wrong type, or unknown sub.
    """
    if creds is None:
        raise _unauthorized()
    try:
        payload = decode_token(creds.credentials, expected_type="access")
    except jwt.PyJWTError:
        raise _unauthorized()
    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise _unauthorized()
    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise _unauthorized()
    with get_session() as session:
        user = session.execute(
            select(UserRow).where(UserRow.id == user_id)
        ).scalar_one_or_none()
    if user is None:
        raise _unauthorized()
    return user
