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
from app.db.mongodb import mongo_repository

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


