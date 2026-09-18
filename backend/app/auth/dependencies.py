from typing import Optional
from fastapi import Header, HTTPException, status, Depends
from app.auth.models import AuthenticatedUser
from app.auth.token_verifier import verify_token_cryptographic


def get_current_user_token(authorization: Optional[str] = Header(None)) -> str:
    """Extract Bearer token from Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must follow 'Bearer <token>' format.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return parts[1]


def get_current_user(token: str = Depends(get_current_user_token)) -> AuthenticatedUser:
    """FastAPI dependency: Returns cryptographically verified AuthenticatedUser.

    Rejects unauthenticated, expired, or invalid tokens.
    Derives user ID strictly from the verified token.
    """
    return verify_token_cryptographic(token)


def get_optional_current_user(authorization: Optional[str] = Header(None)) -> Optional[AuthenticatedUser]:
    """Optional authentication dependency for hybrid endpoints."""
    if not authorization:
        return None
    try:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return verify_token_cryptographic(parts[1])
    except Exception:
        pass
    return None
