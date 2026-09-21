from __future__ import annotations
import time
"""VisionGuard Multi-Surface Notification Delivery API.

Endpoints for Web Push VAPID key exchange, device registration, unregistration,
and test notification dispatches across Desktop and Mobile surfaces.
"""


from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.alerts.mobile_push_provider import mobile_push_provider
from app.db.mongodb import mongo_repository, UserRepository

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class DeviceRegistrationRequest(BaseModel):
    platform: str = Field(default="web_mobile", description="Device platform (ios, android, web_mobile, windows_desktop)")
    device_name: str = Field(default="Mobile Device", description="Human friendly device name")
    push_subscription: Dict[str, Any] = Field(..., description="W3C Web Push Subscription object")


class TestNotificationResponse(BaseModel):
    status: str
    surface: str
    message: str
    delivery_summary: Optional[Dict[str, Any]] = None


@router.get("/vapid-public-key", summary="Get VAPID public key for Web Push subscription")
async def get_vapid_public_key() -> Dict[str, str]:
    """Return the VAPID public key needed by browser PushManager."""
    return {"public_key": mobile_push_provider.public_key, "vapid_public_key": mobile_push_provider.public_key}


@router.get("/devices", summary="List registered notification devices for authenticated user")
async def list_devices(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """List all registered devices owned strictly by authenticated user (secrets sanitized)."""
    return mongo_repository.notification_devices.get_user_devices(
        user_id=current_user.id,
        enabled_only=False,
        sanitize=True,
    )


@router.post("/devices/register", status_code=status.HTTP_201_CREATED, summary="Register mobile device for push")
async def register_device(
    req: DeviceRegistrationRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Register or update a push device under the authenticated user's account."""
    if not req.push_subscription or not req.push_subscription.get("endpoint"):
        raise HTTPException(status_code=400, detail="Invalid push subscription payload.")

    device = mongo_repository.notification_devices.register_device(
        user_id=current_user.id,
        platform=req.platform,
        device_name=req.device_name,
        push_subscription=req.push_subscription,
        enabled=True,
    )
    device_id = device.get("device_id") or device.get("_id")
    return {"status": "REGISTERED", "device_id": device_id, "device": device}


@router.delete("/devices/{device_id}", summary="Unregister a device")
async def unregister_device(
    device_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Unregister a device owned strictly by the authenticated user."""
    success = mongo_repository.notification_devices.unregister_device(
        user_id=current_user.id,
        device_id=device_id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Device not found or not owned by user.")
    return {"status": "UNREGISTERED", "device_id": device_id}


@router.post("/test-mobile", summary="Send test mobile push notification")
async def test_mobile(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> TestNotificationResponse:
    """Send an authentic test notification to the authenticated user's registered mobile devices."""
    res = mobile_push_provider.send_test_push(user_id=current_user.id)
    return TestNotificationResponse(
        status="DISPATCHED",
        surface="MOBILE_PUSH",
        message="Test mobile push dispatched.",
        delivery_summary=res,
    )


@router.post("/test-desktop", summary="Confirm test desktop notification")
async def test_desktop() -> TestNotificationResponse:
    """Return confirmation directive for browser to display a test desktop notification."""
    return TestNotificationResponse(
        status="CONFIRMED",
        surface="DESKTOP_NOTIFICATION",
        message="Desktop notification test directive issued.",
    )

_test_sms_cooldown: Dict[str, float] = {}


@router.post("/test-sms", summary="Send test SMS alert to verified mobile number")
async def test_sms(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> TestNotificationResponse:
    """Send an authentic test SMS alert strictly to the authenticated user's verified phone number.

    Security guarantees:
    - Never accepts destination phone number from client request body.
    - Resolves phone number exclusively from authenticated user database record.
    - Requires phone_verified == True and sms_alerts_enabled == True.
    - Enforces 60-second rate limiting cooldown.
    """
    user_repo = UserRepository()
    user = user_repo.get_by_id(current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    phone = user.get("phone_number")
    phone_verified = bool(user.get("phone_verified", False))

    if not phone or not phone_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No verified phone number found on account. Please verify your mobile number first.",
        )

    # Check preferences
    prefs = mongo_repository.preferences.get_user_preferences(current_user.id)
    if prefs and not prefs.get("sms_alerts_enabled", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SMS alerts are disabled in your notification settings.",
        )

    # Rate limiting: 60s cooldown
    now = time.time()
    last_sent = _test_sms_cooldown.get(current_user.id, 0.0)
    if now - last_sent < 60.0:
        remaining = int(60.0 - (now - last_sent))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {remaining} seconds before requesting another test SMS.",
        )

    from app.notifications.sms_provider import sms_provider
    from app.notifications.phone_utils import mask_phone_number

    if not sms_provider.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Phone verification service is currently unavailable",
        )

    msg = "VisionGuard Test Alert: Your verified mobile number is connected and receiving real-time safety alerts."
    try:
        success = sms_provider.send_alert(phone, msg)
        if success:
            _test_sms_cooldown[current_user.id] = now
            return TestNotificationResponse(
                status="DELIVERED",
                surface="SMS",
                message=f"Test SMS dispatched to {mask_phone_number(phone)}.",
                delivery_summary={"recipient": mask_phone_number(phone), "phone_verified": True},
            )
        raise HTTPException(status_code=500, detail="SMS provider failed to deliver message.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send test SMS: {str(e)}")
