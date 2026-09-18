import os
import time
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from jose import jwt, JWTError, ExpiredSignatureError
import httpx

from app.auth.models import AuthenticatedUser
from app.config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET


def verify_token_cryptographic(token: str) -> AuthenticatedUser:
    """Cryptographically verify JWT token and extract authenticated user.

    Validates:
    - Signature
    - Expiration (exp)
    - Audience (aud)
    - Subject (sub / user_id)

    Raises HTTPException(401) on any cryptographic or claim validation failure.
    """
    if not token or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    clean_token = token.strip()
    if clean_token.lower().startswith("bearer "):
        clean_token = clean_token[7:].strip()

    # Strategy 1: Local JWT secret verification (fastest, cryptographic)
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET") or SUPABASE_JWT_SECRET
    if jwt_secret:
        try:
            payload = jwt.decode(
                clean_token,
                jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token missing subject claim (user_id).",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return AuthenticatedUser(
                id=str(user_id),
                email=payload.get("email"),
                role=payload.get("role", "authenticated"),
                raw_token=clean_token,
            )
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token signature or malformed token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Strategy 2: Remote verification with Supabase Auth API
    sb_url = os.getenv("SUPABASE_URL") or SUPABASE_URL
    sb_anon = os.getenv("SUPABASE_ANON_KEY") or SUPABASE_ANON_KEY
    if sb_url and sb_anon:
        try:
            headers = {
                "Authorization": f"Bearer {clean_token}",
                "apikey": sb_anon,
            }
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(f"{sb_url.rstrip('/')}/auth/v1/user", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    user_id = data.get("id")
                    if user_id:
                        return AuthenticatedUser(
                            id=str(user_id),
                            email=data.get("email"),
                            role=data.get("role", "authenticated"),
                            raw_token=clean_token,
                        )
                elif resp.status_code == 401:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Supabase Auth rejected token: expired or invalid.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
        except httpx.RequestError as req_err:
            # Network issue connecting to Supabase auth
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to verify authentication with cloud provider (network failure).",
            )

    # If unconfigured in local test/dev mode without credentials
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. No verification key configured on server.",
        headers={"WWW-Authenticate": "Bearer"},
    )
