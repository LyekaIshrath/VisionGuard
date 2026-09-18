from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any

from app.camera.manager import get_camera_manager, CameraManager
from app.perception.engine import get_perception_engine, PerceptionEngine

router = APIRouter(prefix="/posture", tags=["posture"])


def get_manager() -> CameraManager:
    return get_camera_manager()


def get_engine() -> PerceptionEngine:
    return get_perception_engine()


@router.post("/calibration/start", summary="Start posture calibration")
async def start_calibration(
    manager: CameraManager = Depends(get_manager),
    engine: PerceptionEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Initiate posture calibration.

    Requires monitoring to be running and person + pose to be actively detected.
    """
    cam_status = manager.status()
    if cam_status.get("state") != "RUNNING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Monitoring must be running to start posture calibration.",
        )

    latest_state = engine.get_latest_state()
    if not latest_state.pose_detected or not latest_state.person_detected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Person and pose must be detected to start posture calibration.",
        )

    res = engine.calibration_service.start_calibration()
    return res


@router.get("/calibration/status", summary="Get posture calibration status")
async def get_calibration_status(
    engine: PerceptionEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Return truthful calibration progress, sample count, state, quality, and failure reason."""
    return engine.calibration_service.get_status()


@router.post("/calibration/reset", summary="Reset posture calibration")
async def reset_calibration(
    engine: PerceptionEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Completely invalidate baseline and reset calibration to IDLE."""
    engine.reset_posture()
    return {"status": "RESET", "state": "IDLE"}
