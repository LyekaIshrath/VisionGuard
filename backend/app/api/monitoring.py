import numpy as np

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
from app.coordination.coordinator import get_monitoring_coordinator, MonitoringCoordinator



router = APIRouter(tags=["monitoring"])





def get_manager() -> CameraManager:

    return get_camera_manager()





def get_coordinator() -> MonitoringCoordinator:
    return get_monitoring_coordinator()


def get_perception() -> PerceptionEngine:

    return get_perception_engine()





@router.post("/monitoring/start", summary="Start unified local monitoring session")
async def monitoring_start(
    coordinator: MonitoringCoordinator = Depends(get_coordinator),
    manager: CameraManager = Depends(get_manager),
    user: Optional[AuthenticatedUser] = Depends(get_optional_current_user),
):
    """Atomically start all monitoring subsystems under a single session."""
    user_id = user.id if user else None
    token = user.token if user else None
    result = coordinator.start_monitoring(user_id=user_id, token=token)
    if not result.get("success", False) and result.get("status") != "ALREADY_RUNNING":
        raise HTTPException(status_code=500, detail=result)
    return {
        "status": result.get("status", "STARTED"),
        "session_id": result.get("session_id"),
        "started_at": result.get("started_at"),
        "baseline_source": result.get("baseline_source", "BUILT_IN"),
        "camera_index": manager.camera_index,
    }


@router.post("/monitoring/stop", summary="Stop monitoring and release camera")
async def monitoring_stop(
    coordinator: MonitoringCoordinator = Depends(get_coordinator),
):
    """Atomically stop monitoring and finalize session report."""
    res = coordinator.stop_monitoring()
    return {
        "status": res.get("status", "STOPPED"),
        "session_id": res.get("session_id"),
        "session_summary": res.get("session_summary"),
        "timeline_events_count": res.get("timeline_events_count", 0),
        "timeline_events": res.get("timeline_events", coordinator.get_timeline()),
    }


@router.get("/monitoring/timeline", summary="Return event timeline for active session")
async def monitoring_timeline(
    coordinator: MonitoringCoordinator = Depends(get_coordinator),
):
    """Return timestamped state-transition and risk events for current session."""
    return {"events": coordinator.timeline_events}





@router.get("/monitoring/status", summary="Return actual monitoring/camera/perception state")

async def monitoring_status(
    manager: CameraManager = Depends(get_manager),
    perception: PerceptionEngine = Depends(get_perception),
):

    """Return the actual state of monitoring, camera, and perception services."""

    status = manager.status()
    status["inference_fps"] = perception.inference_hz
    return status





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



                raw_frame = manager.get_latest_raw_frame_only()

                if mode == "OFF":

                    if raw_frame is not None and isinstance(raw_frame, np.ndarray):

                        import cv2

                        ok, buf = cv2.imencode(".jpg", raw_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])

                        frame_bytes = buf.tobytes() if ok else None

                    else:

                        frame_bytes = manager.get_latest_frame()

                else:

                    valid_raw = raw_frame if isinstance(raw_frame, np.ndarray) else None

                    frame_bytes = perception.get_annotated_frame_bytes(mode, current_frame=valid_raw)

                    if frame_bytes is None:

                        frame_bytes = manager.get_latest_frame()



                if frame_bytes is not None:

                    yield (

                        b"--frame\r\n"

                        b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"

                    )

                await asyncio.sleep(0.033)  # ~30 FPS responsive preview without artificial ceiling

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
    coordinator: MonitoringCoordinator = Depends(get_coordinator),
):

    """WebSocket endpoint streaming real-time HumanState updates."""

    await websocket.accept()



    # Worker runs independently; perception consumes newest frames



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
                    "recent_events": [
                        {
                            "event_id": ev.event_id,
                            "timestamp": ev.timestamp.isoformat() if hasattr(ev.timestamp, "isoformat") else str(ev.timestamp),
                            "category": ev.category.value if hasattr(ev.category, "value") else str(ev.category),
                            "status": ev.status.value if hasattr(ev.status, "value") else str(ev.status),
                            "risk_level": ev.risk_level.value if hasattr(ev.risk_level, "value") else str(ev.risk_level),
                            "risk_score": ev.risk_score,
                            "message": ev.message,
                            "reason_codes": [r.value if hasattr(r, "value") else str(r) for r in (ev.reason_codes or [])],
                            "duration_sec": ev.duration_sec,
                        }
                        for ev in list(engine.intervention_engine.event_history)
                    ],
                    "session_id": coordinator.session_id,
                    "monitoring_state": coordinator.state.value,
                    "activity_state": state.activity_state or "UNKNOWN",
                    "activity_score": state.activity_score,
                    "activity_confidence": state.activity_confidence,
                    "activity_reason_codes": state.activity_reason_codes or [],
                    "person_present": state.person_detected,
                    "blink_count": state.blink_count or 0,
                    "longest_eye_closure": state.longest_eye_closure or 0.0,
                    "valid_eye_tracking_seconds": state.valid_eye_tracking_seconds or 0.0,
                    "head_yaw": state.head_yaw,
                    "head_roll": state.head_roll,
                    "neck_inclination": state.neck_inclination,
                    "keyboard_activity_count": state.keyboard_activity_count or 0,
                    "mouse_activity_count": state.mouse_activity_count or 0,
                    "idle_seconds": state.idle_seconds or 0.0,
                    "baseline_source": state.baseline_source or "BUILT_IN",
                    "capture_fps": getattr(manager._source, "capture_fps", 0.0) if manager._source else 0.0,
                    "preview_fps": getattr(coordinator, "preview_fps", getattr(coordinator, "_preview_fps", 0.0)),
                    "inference_hz": getattr(engine, "inference_hz", 0.0),
                    "screen_activity_level": getattr(state, "screen_activity_level", "UNKNOWN"),
                    "screen_change_score": getattr(state, "screen_change_score", 0.0),
                    "camera_state": (manager._source.camera_state.value if manager._source and hasattr(manager._source, "camera_state") else "STOPPED"),
                    "last_frame_age_ms": getattr(manager._source, "last_frame_age_ms", 9999.0) if manager._source else 9999.0,

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



