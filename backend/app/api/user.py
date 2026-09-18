from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from app.auth.models import AuthenticatedUser
from app.auth.dependencies import get_current_user
from app.sessions.service import session_service

router = APIRouter(prefix="/user", tags=["user"])

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
