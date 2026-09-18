import os
import time
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from jose import jwt, JWTError, ExpiredSignatureError
import httpx

from app.auth.models import AuthenticatedUser
from app.config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET

# In-memory JWKS cache with TTL and key-rotation support
_jwks_cache: Dict[str, Any] = {}
_jwks_last_fetched: float = 0.0
JWKS_CACHE_TTL: float = 3600.0  # 1 hour cache


def fetch_jwks(supabase_url: str, force: bool = False) -> Dict[str, Any]:
    """Fetch and cache public JWKS keys from Supabase project."""
    global _jwks_cache, _jwks_last_fetched
    now = time.time()
    if not force and _jwks_cache and (now - _jwks_last_fetched < JWKS_CACHE_TTL):
        return _jwks_cache

    endpoint = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(endpoint)
            if resp.status_code == 200:
                keys = resp.json().get("keys", [])
                for k in keys:
                    if "kid" in k:
                        _jwks_cache[k["kid"]] = k
                _jwks_last_fetched = now
                return _jwks_cache
    except Exception:
        if _jwks_cache:
            return _jwks_cache
        raise
    return _jwks_cache


def get_jwks_key(kid: str, supabase_url: str) -> Optional[Dict[str, Any]]:
    """Lookup key by kid in cache, refreshing if not found to handle key rotation."""
    global _jwks_cache
    if kid in _jwks_cache:
        return _jwks_cache[kid]

    # Key not in cache or key rotation: fetch from Supabase
    try:
        fetch_jwks(supabase_url, force=True)
    except Exception:
        pass
    return _jwks_cache.get(kid)


def verify_token_cryptographic(token: str) -> AuthenticatedUser:
    """Cryptographically verify JWT token and extract authenticated user.

    Supports:
    1. Modern Supabase asymmetric keys (ES256 / JWKS) with cryptographic signature,
       issuer, audience, and expiration verification.
    2. Symmetric HS256 secret verification for local testing and backward compatibility.
    3. Remote Supabase Auth API verification fallback.

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

    # Inspect token header unverified to determine signing algorithm and kid
    try:
        header = jwt.get_unverified_header(clean_token)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Malformed token header: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    alg = header.get("alg", "HS256")
    kid = header.get("kid")

    sb_url = os.getenv("SUPABASE_URL") or SUPABASE_URL

    # Strategy 1: Asymmetric ES256 / JWKS Verification (Real Supabase Production Mode)
    if alg == "ES256" or (kid and sb_url):
        if not sb_url:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Supabase URL required for asymmetric JWKS verification.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            key_dict = get_jwks_key(kid, sb_url) if kid else None
            if not key_dict:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Signing key with kid '{kid}' not found in project JWKS.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            expected_issuer = f"{sb_url.rstrip('/')}/auth/v1"
            payload = jwt.decode(
                clean_token,
                key_dict,
                algorithms=["ES256"],
                audience="authenticated",
                issuer=expected_issuer,
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

    # Strategy 2: Local Symmetric Secret Verification (HS256)
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

    # Strategy 3: Remote fallback with Supabase Auth API
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
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to verify authentication with cloud provider (network failure).",
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. No verification key configured on server.",
        headers={"WWW-Authenticate": "Bearer"},
    )
