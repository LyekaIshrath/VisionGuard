from fastapi import APIRouter
from app.sessions.models import CloudStatusResponse
from app.sessions.service import session_service

router = APIRouter(prefix="/cloud", tags=["cloud"])

@router.get("/status", response_model=CloudStatusResponse)
def get_cloud_status() -> CloudStatusResponse:
    """Returns the current state of cloud connectivity and synchronization."""
    return session_service.get_cloud_status()
