"""Alertness API Endpoints.

Provides REST control for personalized alertness calibration lifecycle.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any

from app.camera.manager import get_camera_manager, CameraManager
from app.perception.engine import get_perception_engine, PerceptionEngine

router = APIRouter(prefix="/alertness", tags=["alertness"])


def get_manager() -> CameraManager:
    return get_camera_manager()


def get_engine() -> PerceptionEngine:
    return get_perception_engine()


@router.post("/calibration/start", summary="Start alertness calibration")
async def start_calibration(
    manager: CameraManager = Depends(get_manager),
    engine: PerceptionEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Initiate personal alertness calibration.

    Requires monitoring to be running and face to be actively detected.
    """
    cam_status = manager.status()
    if cam_status.get("state") != "RUNNING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Monitoring must be running to start alertness calibration.",
        )

    latest_state = engine.get_latest_state()
    if not latest_state.face_detected or not latest_state.person_detected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Person and face must be detected to start alertness calibration.",
        )

    res = engine.alertness_calibration_service.start_calibration()
    return res


@router.get("/calibration/status", summary="Get alertness calibration status")
async def get_calibration_status(
    engine: PerceptionEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Return truthful calibration progress, sample count, state, quality, and failure reason."""
    return engine.alertness_calibration_service.get_status()


@router.post("/calibration/reset", summary="Reset alertness calibration")
async def reset_calibration(
    engine: PerceptionEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Completely invalidate baseline and reset calibration to IDLE."""
    engine.reset_alertness()
    return {"status": "RESET", "state": "IDLE"}

@router.get("/candidates", summary="Get recent blink candidate events for verification")
def get_blink_candidates(engine: PerceptionEngine = Depends(get_engine)):
    analyzer = engine.alertness_analyzer
    candidates = list(analyzer.candidate_history) if hasattr(analyzer, "candidate_history") else []
    return {
        "total_blink_count": analyzer._total_blink_count,
        "longest_eye_closure": analyzer._longest_eye_closure,
        "threshold_min": analyzer._config.blink_min_duration_sec,
        "threshold_max": analyzer._config.blink_max_duration_sec,
        "candidates": candidates,
    }
