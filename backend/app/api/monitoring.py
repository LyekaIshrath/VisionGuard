import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import StreamingResponse
from starlette.websockets import WebSocketState
from app.camera.manager import get_camera_manager, CameraManager
from app.perception.engine import get_perception_engine, PerceptionEngine
from app.auth.models import AuthenticatedUser
from app.auth.dependencies import get_optional_current_user
from app.sessions.service import session_service

router = APIRouter(tags=["monitoring"])


def get_manager() -> CameraManager:
    return get_camera_manager()


def get_perception() -> PerceptionEngine:
    return get_perception_engine()


@router.post("/monitoring/start", summary="Start webcam monitoring")
async def monitoring_start(
    manager: CameraManager = Depends(get_manager),
    perception: PerceptionEngine = Depends(get_perception),
    user: Optional[AuthenticatedUser] = Depends(get_optional_current_user),
):
    """Start webcam monitoring and hook authoritative perception pipeline."""
    result = manager.start()
    if result in ("STARTED", "ALREADY_RUNNING"):
        perception.reset_session()
        user_id = user.id if user else None
        token = user.token if user else None
        session_service.start_session(user_id=user_id, token=token)
        manager.on_frame(perception.process_frame)
    return {"status": result, "camera_index": manager.camera_index}


@router.post("/monitoring/stop", summary="Stop monitoring and release camera")
async def monitoring_stop(
    manager: CameraManager = Depends(get_manager),
    perception: PerceptionEngine = Depends(get_perception),
):
    """Stop monitoring and release the camera."""
    session_summary = session_service.stop_session()
    perception.stop_session()
    result = manager.stop()
    return {"status": result, "session_summary": session_summary}


@router.get("/monitoring/status", summary="Return actual monitoring/camera/perception state")
async def monitoring_status(manager: CameraManager = Depends(get_manager)):
    """Return the actual state of monitoring, camera, and perception services."""
    return manager.status()


@router.get("/monitoring/preview", summary="Live camera preview stream (MJPEG)")
async def monitoring_preview(
    overlay: str = "MINIMAL",
    manager: CameraManager = Depends(get_manager),
    perception: PerceptionEngine = Depends(get_perception),
):
    """Stream live webcam frames as multipart/x-mixed-replace MJPEG.

    Reuses existing WebcamSource frames without opening a second VideoCapture.
    Supports overlay query parameter: 'OFF', 'MINIMAL' (default), 'DEBUG'.
    """
    status = manager.status()
    if status.get("state") not in ("RUNNING", "NO_FRAMES"):
        raise HTTPException(
            status_code=503,
            detail="Camera monitoring is not active. Start monitoring to view preview."
        )

    if not isinstance(manager, CameraManager):
        manager = get_manager()
    if not isinstance(perception, PerceptionEngine):
        perception = get_perception()

    mode = overlay.upper() if overlay else "MINIMAL"
    if mode not in ("OFF", "MINIMAL", "DEBUG"):
        mode = "MINIMAL"

    async def frame_generator():
        try:
            while True:
                current_status = manager.status()
                if current_status.get("state") not in ("RUNNING", "NO_FRAMES"):
                    break

                if mode == "OFF":
                    frame_bytes = manager.get_latest_frame()
                else:
                    frame_bytes = perception.get_annotated_frame_bytes(mode)
                    if frame_bytes is None:
                        frame_bytes = manager.get_latest_frame()

                if frame_bytes is not None:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                    )
                await asyncio.sleep(0.07)  # ~14 FPS preview
        except (asyncio.CancelledError, GeneratorExit):
            pass

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# WebSocket endpoint for real-time human state updates
@router.websocket("/monitoring/ws")
async def monitoring_ws(
    websocket: WebSocket,
    manager: CameraManager = Depends(get_manager),
    engine: PerceptionEngine = Depends(get_perception),
):
    """WebSocket endpoint streaming real-time HumanState updates."""
    await websocket.accept()

    # Ensure perception is hooked to frame stream
    manager.on_frame(engine.process_frame)

    # Send initial status
    try:
        status = manager.status()
        await websocket.send_json({"type": "status", "data": status})
    except Exception:
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass
        return

    # Background pusher for real-time human state updates (~10 Hz)
    async def stream_human_state():
        while websocket.client_state == WebSocketState.CONNECTED:
            try:
                state = engine.get_latest_state()
                risk_state = engine.risk_engine.latest_state
                active_inv = engine.intervention_engine.active_intervention
                data = {
                    "timestamp": state.timestamp.isoformat() if state.timestamp else None,
                    "track_id": state.track_id,
                    "person_detected": state.person_detected,
                    "face_detected": state.face_detected,
                    "pose_detected": state.pose_detected,
                    "posture_status": state.posture_status,
                    "posture_score": state.posture_score,
                    "alertness_status": state.alertness_status,
                    "alertness_score": state.alertness_score,
                    "eye_state": state.eye_state,
                    "eye_closure_duration": state.eye_closure_duration,
                    "blink_rate": state.blink_rate,
                    "yawn_score": state.yawn_score,
                    "head_pitch": state.head_pitch,
                    "risk_level": state.risk_level,
                    "risk_score": state.risk_score,
                    "posture_risk": risk_state.posture_risk.level.value if risk_state and risk_state.posture_risk else None,
                    "alertness_risk": risk_state.alertness_risk.level.value if risk_state and risk_state.alertness_risk else None,
                    "active_reasons": [r.value for r in risk_state.active_reasons] if risk_state else [],
                    "active_intervention": (
                        {
                            "intervention_id": active_inv.intervention_id,
                            "category": active_inv.category.value,
                            "level": active_inv.level.value,
                            "title": active_inv.title,
                            "message": active_inv.message,
                        }
                        if active_inv
                        else None
                    ),
                    "confidence": state.confidence,
                }
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"type": "human_state", "data": data})
                await asyncio.sleep(0.1)
            except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
                break
            except Exception:
                break

    push_task = asyncio.create_task(stream_human_state())

    try:
        while websocket.client_state == WebSocketState.CONNECTED:
            # Handle incoming client messages / keepalive
            data_text = await websocket.receive_text()
            if websocket.client_state == WebSocketState.CONNECTED:
                status = manager.status()
                await websocket.send_json({"type": "status", "data": status})
    except WebSocketDisconnect:
        # Client gracefully or ungracefully disconnected (e.g. browser refresh/navigation)
        pass
    except RuntimeError as re:
        # Catch normal disconnect / already closed runtime errors from Starlette
        if "disconnect" not in str(re).lower() and "close" not in str(re).lower():
            raise
    finally:
        push_task.cancel()
        try:
            await push_task
        except (asyncio.CancelledError, Exception):
            pass

        # Only close if still connected from the server perspective and client hasn't closed
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass

