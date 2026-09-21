"""VisionGuard Application Authentication Endpoints.

Pure server-side authentication backed by MongoDB.
Provides:
- 2-step OTP Verified Phone Registration:
    1. POST /auth/register/start -> validates info, sends OTP to mobile number.
    2. POST /auth/register/verify -> verifies OTP, creates activated account with phone_verified=True.
    3. POST /auth/register/resend-otp -> resends OTP with 60s cooldown.
- Phone Change Flow:
    1. POST /auth/phone/start-change -> sends OTP to new phone number.
    2. POST /auth/phone/verify-change -> verifies OTP, updates user phone.
- Standard login, me, and logout.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from app.auth.models import AuthenticatedUser
from app.auth.dependencies import get_current_user
from app.auth.service import hash_password, verify_password, create_access_token
from app.db.mongodb import UserRepository, mongo_repository
from app.notifications.phone_utils import normalize_phone_number, mask_phone_number
from app.notifications.sms_provider import sms_provider

router = APIRouter(prefix="/auth", tags=["auth"])
user_repo = UserRepository()

EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-\.]+$")


class RegisterStartRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=100)
    name: Optional[str] = Field(default=None, max_length=100)
    email: str
    phone_number: str
    password: str = Field(min_length=6, description="Minimum 6 characters")
    confirm_password: Optional[str] = None


class RegisterVerifyRequest(BaseModel):
    phone_number: str
    code: str = Field(min_length=4, max_length=10)


class ResendOtpRequest(BaseModel):
    phone_number: str


class PhoneChangeStartRequest(BaseModel):
    new_phone_number: str


class PhoneChangeVerifyRequest(BaseModel):
    new_phone_number: str
    code: str = Field(min_length=4, max_length=10)


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=6, description="Minimum 6 characters")
    display_name: Optional[str] = None
    phone_number: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


# =========================================================================
# 1. 2-Step Verified Phone Registration
# =========================================================================

@router.post("/register/start", status_code=status.HTTP_200_OK)
def register_start(req: RegisterStartRequest) -> Dict[str, Any]:
    """Step 1: Validate account info, verify phone availability, and send OTP."""
    norm_email = req.email.strip().lower()
    full_name = (req.full_name or req.name or norm_email.split("@")[0]).strip()
    norm_email = req.email.strip().lower()
    if not EMAIL_REGEX.match(norm_email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format.",
        )

    if req.confirm_password is not None and req.password != req.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match.",
        )

    if len(req.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long.",
        )

    try:
        canonical_phone = normalize_phone_number(req.phone_number)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )

    # Check email duplicate
    existing_user = user_repo.get_by_email(norm_email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    # Check phone duplicate (verified)
    db = mongo_repository.client.db
    if db is not None:
        dup_phone = db.users.find_one({"phone_number": canonical_phone, "phone_verified": True})
        if dup_phone:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Phone number '{mask_phone_number(canonical_phone)}' is already registered and verified.",
            )

    # Hash password safely before saving in pending verifications
    pwd_hash = hash_password(req.password)

    # Dispatch OTP via configured provider
    if not sms_provider.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Phone verification service is currently unavailable",
        )
    try:
        res = sms_provider.send_verification(canonical_phone)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS if "wait" in str(ve).lower() else status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send SMS verification: {str(e)}",
        )

    # Attach pending registration credentials to the verification record
    if db is not None:
        db.phone_verifications.update_one(
            {"phone_number": canonical_phone, "verified": False},
            {
                "$set": {
                    "pending_registration": {
                        "email": norm_email,
                        "display_name": full_name,
                        "password_hash": pwd_hash,
                    }
                }
            },
        )

    return {
        "status": "OTP_SENT",
        "phone_number_masked": res.get("phone_number_masked", mask_phone_number(canonical_phone)),
        "expires_in_seconds": res.get("expires_in_seconds", 300),
        "resend_cooldown_seconds": res.get("resend_cooldown_seconds", 60),
    }


@router.post("/register/verify", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register_verify(req: RegisterVerifyRequest) -> AuthResponse:
    """Step 2: Verify user-provided OTP, activate account with phone_verified=True, and issue JWT."""
    try:
        canonical_phone = normalize_phone_number(req.phone_number)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    db = mongo_repository.client.db
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database unavailable.")

    # Retrieve pending registration record
    pending_rec = db.phone_verifications.find_one(
        {"phone_number": canonical_phone, "verified": False},
        sort=[("created_at", -1)],
    )

    if not pending_rec:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending registration found for this phone number. Please start registration again.",
        )

    reg_data = pending_rec.get("pending_registration")
    if not reg_data or not reg_data.get("email") or not reg_data.get("password_hash"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration session expired or corrupted. Please start registration again.",
        )

    # Verify OTP
    try:
        verified = sms_provider.verify_code(canonical_phone, req.code)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Verification error: {e}")

    if not verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")

    # Create active verified user
    try:
        user = user_repo.create_user(
            email=reg_data["email"],
            password_hash=reg_data["password_hash"],
            display_name=reg_data.get("display_name"),
            phone_number=canonical_phone,
            phone_verified=True,
            phone_verified_at=datetime.now(timezone.utc),
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create account: {e}")

    token = create_access_token(user_id=user["id"], email=reg_data["email"])

    # Attach masked phone to response user dict
    user["phone_number"] = canonical_phone
    user["phone_masked"] = mask_phone_number(canonical_phone)
    user["phone_verified"] = True

    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=user,
    )


@router.post("/register/resend-otp", status_code=status.HTTP_200_OK)
def register_resend_otp(req: ResendOtpRequest) -> Dict[str, Any]:
    """Resend OTP to phone number enforcing 60s cooldown."""
    try:
        canonical_phone = normalize_phone_number(req.phone_number)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    db = mongo_repository.client.db
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database unavailable.")

    pending_rec = db.phone_verifications.find_one(
        {"phone_number": canonical_phone, "verified": False},
        sort=[("created_at", -1)],
    )
    if not pending_rec:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active registration session found.")

    saved_reg_data = pending_rec.get("pending_registration")

    if not sms_provider.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Phone verification service is currently unavailable",
        )
    try:
        res = sms_provider.send_verification(canonical_phone)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS if "wait" in str(ve).lower() else status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )

    # Re-attach registration data to new pending verification
    if saved_reg_data:
        db.phone_verifications.update_one(
            {"phone_number": canonical_phone, "verified": False},
            {"$set": {"pending_registration": saved_reg_data}},
        )

    return res


# =========================================================================
# 2. Phone Change Flow (Authenticated)
# =========================================================================

@router.post("/phone/start-change", status_code=status.HTTP_200_OK)
def phone_change_start(
    req: PhoneChangeStartRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Initiate phone number update with OTP verification on new number."""
    try:
        canonical_phone = normalize_phone_number(req.new_phone_number)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    db = mongo_repository.client.db
    if db is not None:
        # Check if already verified by another user
        dup = db.users.find_one({
            "phone_number": canonical_phone,
            "phone_verified": True,
            "_id": {"$ne": str(current_user.id)},
        })
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Phone number '{mask_phone_number(canonical_phone)}' is already verified by another user.",
            )

    if not sms_provider.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Phone verification service is currently unavailable",
        )
    try:
        res = sms_provider.send_verification(canonical_phone)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS if "wait" in str(ve).lower() else status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )

    # Link user_id to this verification
    if db is not None:
        db.phone_verifications.update_one(
            {"phone_number": canonical_phone, "verified": False},
            {"$set": {"user_id": current_user.id, "purpose": "PHONE_CHANGE"}},
        )

    return res


@router.post("/phone/verify-change", status_code=status.HTTP_200_OK)
def phone_change_verify(
    req: PhoneChangeVerifyRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Verify OTP and update user's verified phone number."""
    try:
        canonical_phone = normalize_phone_number(req.new_phone_number)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    try:
        verified = sms_provider.verify_code(canonical_phone, req.code)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    if not verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")

    try:
        updated = user_repo.update_phone(user_id=current_user.id, phone_number=canonical_phone, verified=True)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve))

    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update phone number.")

    return {
        "status": "UPDATED",
        "phone_number": canonical_phone,
        "phone_masked": mask_phone_number(canonical_phone),
        "phone_verified": True,
    }


# =========================================================================
# 3. Standard Login, Legacy Register, Me & Logout
# =========================================================================

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest) -> AuthResponse:
    """Legacy/direct registration (phone_verified defaults to False unless verified via OTP)."""
    norm_email = req.email.strip().lower()
    full_name = (req.display_name or norm_email.split("@")[0]).strip()
    norm_email = req.email.strip().lower()
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
            display_name=req.display_name,
            phone_number=req.phone_number,
            phone_verified=False,
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

    phone = user.get("phone_number")
    user_data = {
        "id": user_id,
        "_id": user_id,
        "email": norm_email,
        "display_name": user.get("display_name") or norm_email.split("@")[0],
        "phone_number": phone,
        "phone_masked": mask_phone_number(phone) if phone else "",
        "phone_verified": bool(user.get("phone_verified", False)),
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
    """Retrieve authenticated user profile with masked phone representation."""
    user = user_repo.get_by_id(current_user.id)
    if not user:
        return {
            "id": current_user.id,
            "email": current_user.email,
            "display_name": (current_user.email or "User").split("@")[0],
            "phone_masked": "",
            "phone_verified": False,
            "status": "ACTIVE",
        }
    return user


@router.post("/logout")
def logout() -> Dict[str, Any]:
    """Client token discard confirmation."""
    return {"status": "ok", "message": "Logged out successfully."}
