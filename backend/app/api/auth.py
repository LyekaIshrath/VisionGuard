"""VisionGuard Application Authentication Endpoints.

Pure server-side authentication backed by MongoDB.
Provides:
- Direct email/password registration with display name.
- Standard email/password login issuing HS256 JWT access tokens.
- User profile retrieval (/me) and client logout.
"""

from __future__ import annotations

import re
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from app.auth.models import AuthenticatedUser
from app.auth.dependencies import get_current_user
from app.auth.service import hash_password, verify_password, create_access_token
from app.db.mongodb import UserRepository

router = APIRouter(prefix="/auth", tags=["auth"])
user_repo = UserRepository()

EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-\.]+$")


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=6, description="Minimum 6 characters")
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest) -> AuthResponse:
    """Register a new user account with email and password."""
    norm_email = req.email.strip().lower()
    full_name = (req.display_name or norm_email.split("@")[0]).strip()

    if not EMAIL_REGEX.match(norm_email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format.")

    if len(req.password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 6 characters long.")

    existing = user_repo.get_by_email(norm_email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email address already exists.")

    pwd_hash = hash_password(req.password)
    try:
        user = user_repo.create_user(
            email=norm_email,
            password_hash=pwd_hash,
            display_name=full_name,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve))

    token = create_access_token(user_id=user["id"], email=norm_email)
    return AuthResponse(access_token=token, token_type="bearer", user=user)


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest) -> AuthResponse:
    """Authenticate user against MongoDB and issue JWT access token."""
    norm_email = req.email.strip().lower()
    user = user_repo.get_by_email(norm_email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    pwd_hash = user.get("password_hash")
    if not pwd_hash or not verify_password(req.password, pwd_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = user["id"]
    token = create_access_token(user_id=user_id, email=norm_email)

    user_data = {
        "id": user_id,
        "_id": user_id,
        "email": norm_email,
        "display_name": user.get("display_name") or norm_email.split("@")[0],
        "status": user.get("status", "ACTIVE"),
    }

    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=user_data,
    )


@router.get("/me", response_model=Dict[str, Any])
def get_current_user_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve authenticated user profile."""
    user = user_repo.get_by_id(current_user.id)
    if not user:
        return {
            "id": current_user.id,
            "email": current_user.email,
            "display_name": (current_user.email or "User").split("@")[0],
            "status": "ACTIVE",
        }
    # Sanitize password_hash if present
    user.pop("password_hash", None)
    return user


@router.post("/logout")
def logout() -> Dict[str, Any]:
    """Client token discard confirmation."""
    return {"status": "ok", "message": "Logged out successfully."}
