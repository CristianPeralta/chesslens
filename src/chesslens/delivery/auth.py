"""Auth routes: register, login, refresh.

WHY: Kept separate from api.py — auth is a distinct concern (crypto, tokens,
user CRUD). Keeps api.py focused on data routes; auth surface is reviewable
in isolation.
"""
from datetime import datetime, timezone

import jwt as pyjwt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from chesslens.db.models import UserRow
from chesslens.db.session import get_session
from chesslens.delivery.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# WHY: pre-computed bcrypt hash used in the anti-enumeration dummy verify path.
# Must be a valid hash — bcrypt rejects malformed hashes with ValueError which
# would leak a timing difference vs. the unknown-email path.
_DUMMY_HASH = "$2b$12$e8C8IDoHvxvT91Rb1PW4i.tmH3rd/lx0rjwjxkg.YocnRU77y0F8K"


# ---------------------------------------------------------------------------
# Request/Response models (delivery-layer DTOs — never in core/)
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: str
    password: str
    chess_username: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class RegisterResponse(BaseModel):
    id: int
    email: str
    chess_username: str
    created_at: datetime


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=RegisterResponse)
def register(body: RegisterRequest):
    """Create a new user account.

    Returns 201 with public user fields (no tokens, no password hash).
    Returns 409 if email is already registered.
    Returns 422 if password is shorter than 8 characters (Pydantic validator).
    """
    # WHY: normalize email before storage so "Alice@Example.COM" and
    # "alice@example.com" are treated as the same account.
    email = body.email.strip().lower()
    chess_username = body.chess_username.strip().lower()

    password_hash = hash_password(body.password)
    user = UserRow(
        email=email,
        password_hash=password_hash,
        chess_username=chess_username,
        created_at=datetime.now(timezone.utc),
    )

    try:
        with get_session() as session:
            session.add(user)
            session.flush()
            # Refresh inside the session so we can read the generated id
            session.refresh(user)
            # Detach the values we need before the session closes
            user_id = user.id
            user_email = user.email
            user_chess_username = user.chess_username
            user_created_at = user.created_at
    except IntegrityError:
        # WHY: fallback for race condition where two requests slip past the
        # pre-check simultaneously — the DB unique constraint is the authority.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    return RegisterResponse(
        id=user_id,
        email=user_email,
        chess_username=user_chess_username,
        created_at=user_created_at,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    """Authenticate a user and return access + refresh tokens.

    Returns 401 for both unknown email and wrong password — identical response
    body to prevent user enumeration (NFR-02). A dummy bcrypt verify call is
    performed for the unknown-email path to mitigate timing side-channels.
    """
    email = body.email.strip().lower()

    with get_session() as session:
        user = session.execute(
            select(UserRow).where(UserRow.email == email)
        ).scalar_one_or_none()

    if user is None:
        # WHY: dummy bcrypt verify prevents timing attack — see module-level _DUMMY_HASH.
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return TokenResponse(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(user),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest):
    """Issue new access + refresh tokens given a valid refresh token.

    Both tokens are rotated. The old refresh token is NOT invalidated
    (stateless JWT — no revocation list in this slice; see design §3).
    Returns 401 for expired, invalid, wrong-type, or orphan-sub tokens.
    """
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except pyjwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    with get_session() as session:
        user = session.execute(
            select(UserRow).where(UserRow.id == user_id)
        ).scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(user),
    )
