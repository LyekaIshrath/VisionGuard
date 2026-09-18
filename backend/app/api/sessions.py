from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from app.auth.models import AuthenticatedUser
from app.auth.dependencies import get_current_user
from app.sessions.service import session_service
from app.sessions.models import SessionRecord, RiskEventRecord

router = APIRouter(prefix="/sessions", tags=["sessions"])

@router.get("", response_model=List[Dict[str, Any]])
async def list_sessions(
    limit: int = 50,
    offset: int = 0,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Lists monitoring sessions for the authenticated user (enforcing RLS)."""
    try:
        sessions = await session_service.repository.list_sessions(
            token=user.token, limit=limit, offset=offset
        )
        return sessions
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to retrieve sessions from cloud repository: {str(e)}"
        )

@router.get("/{session_id}", response_model=Dict[str, Any])
async def get_session(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Retrieves a single session by ID (RLS enforces user ownership)."""
    try:
        session = await session_service.repository.get_session(
            session_id=session_id, token=user.token
        )
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"
            )
        return session
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to retrieve session: {str(e)}"
        )

@router.get("/{session_id}/events", response_model=List[Dict[str, Any]])
async def get_session_events(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Retrieves risk events associated with a session (RLS enforced)."""
    try:
        events = await session_service.repository.get_session_events(
            session_id=session_id, token=user.token
        )
        return events
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to retrieve session events: {str(e)}"
        )

@router.delete("/{session_id}", response_model=Dict[str, Any])
async def delete_session(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Deletes a session and its cascaded risk events (RLS enforced)."""
    try:
        success = await session_service.repository.delete_session(
            session_id=session_id, token=user.token
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} could not be deleted"
            )
        return {"status": "success", "deleted_session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to delete session: {str(e)}"
        )
