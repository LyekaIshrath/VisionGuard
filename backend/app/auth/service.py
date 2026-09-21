"""VisionGuard Application Authentication Service.

Provides secure server-side password hashing (bcrypt) and HS256 JWT token issuance.
Replaces external Supabase Auth entirely with pure MongoDB-backed authentication.

Invariants:
- Plaintext passwords NEVER stored.
- Password hashes use bcrypt with 12 salt rounds.
- Tokens signed with HS256 using JWT_SECRET from environment.
- Authoritative user_id derived exclusively from verified JWT sub claim.
"""

from __future__ import annotations

import os
import time
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

import bcrypt
from jose import jwt, JWTError, ExpiredSignatureError
from fastapi import HTTPException, status

logger = logging.getLogger("visionguard.auth")

DEFAULT_SECRET = "visionguard-secret-key-development-minimum-32-chars-long"


def get_jwt_secret() -> str:
    """Retrieve JWT signing secret from environment."""
    return os.getenv("JWT_SECRET") or DEFAULT_SECRET


def get_jwt_algorithm() -> str:
    return os.getenv("JWT_ALGORITHM", "HS256")


def hash_password(password: str) -> str:
    """Hash plaintext password with bcrypt (12 rounds)."""
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters long.")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


def create_access_token(
    user_id: str,
    email: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Issue signed HS256 JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
        expire = now + timedelta(minutes=minutes)

    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "email": email.strip().lower(),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "role": "authenticated",
        "iss": "visionguard",
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, get_jwt_secret(), algorithm=get_jwt_algorithm())
    return token


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and cryptographically verify HS256 JWT access token."""
    if not token or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    clean_token = token.strip()
    if clean_token.lower().startswith("bearer "):
        clean_token = clean_token[7:].strip()

    try:
        payload = jwt.decode(
            clean_token,
            get_jwt_secret(),
            algorithms=[get_jwt_algorithm()],
            options={"verify_exp": True, "verify_sub": True},
        )
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: subject (user_id) missing.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
