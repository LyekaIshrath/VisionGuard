from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.models import AuthenticatedUser
from app.auth.dependencies import get_current_user
from app.sessions.service import session_service
from app.alerts.orchestrator import alert_orchestrator

router = APIRouter(prefix="/user", tags=["user"])


class UserPreferencesUpdate(BaseModel):
    browser_notifications_enabled: Optional[bool] = None
    voice_alerts_enabled: Optional[bool] = None
    voice_volume: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    voice_rate: Optional[float] = Field(default=None, ge=0.5, le=2.0)
    voice_pitch: Optional[float] = Field(default=None, ge=0.5, le=2.0)
    quiet_mode_enabled: Optional[bool] = None
    selected_voice: Optional[str] = None
    data_retention_days: Optional[int] = Field(default=None, ge=1)


class AcknowledgeAlertRequest(BaseModel):
    intervention_id: str


@router.get("/preferences", response_model=Dict[str, Any])
async def get_preferences(
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Fetches the authenticated user's preferences, enforcing RLS."""
    try:
        prefs = await session_service.repository.get_user_preferences(
            user_id=user.id, token=user.token
        )
        return prefs
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to retrieve user preferences: {str(e)}"
        )


@router.put("/preferences", response_model=Dict[str, Any])
async def update_preferences(
    payload: UserPreferencesUpdate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Updates the authenticated user's preferences with strict validation."""
    try:
        data = {k: v for k, v in payload.model_dump().items() if v is not None}
        updated = await session_service.repository.upsert_user_preferences(
            user_id=user.id, token=user.token, payload=data
        )
        return updated
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to update user preferences: {str(e)}"
        )


@router.post("/alerts/acknowledge", response_model=Dict[str, Any])
async def acknowledge_alert(
    payload: AcknowledgeAlertRequest,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Records that the user acknowledged an intervention alert.
    Hides presentation without modifying physical RiskEngine metrics.
    """
    alert_orchestrator.acknowledge_alert(payload.intervention_id)
    return {
        "status": "success",
        "intervention_id": payload.intervention_id,
        "message": "Alert acknowledged by user"
    }


@router.delete("/data", response_model=Dict[str, Any])
async def delete_user_data(
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Delete My VisionGuard Data.
    Permanently removes all monitoring sessions, risk events, preferences, and profile.
    NOTE: As per privacy guidelines, this operation deletes all application data,
    while the Supabase Auth login account itself remains active until explicitly deleted in Auth.
    """
    try:
        res = await session_service.repository.delete_user_data(
            user_id=user.id, token=user.token
        )
        return res
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to delete user data: {str(e)}"
        )
