from __future__ import annotations

import threading
from typing import Optional, Callable, Tuple
import numpy as np

from app.camera.source import CameraSource
from app.camera.webcam_source import WebcamSource, CameraState
from app.human_state.models import HumanState


class CameraManager:
    """Manages a single WebcamSource instance lifecycle.

    Controls camera ownership - exactly ONE manager per camera index.
    Provides start/stop/status and truthful diagnostics for monitoring.
    Strictly preserves:
    - Exactly 1 cv2.VideoCapture instance
    - Explicit runtime states (STOPPED, STARTING, LIVE, NO_CAMERA, CAMERA_BUSY, NO_FRAMES, RECONNECTING, ERROR)
    - Safe restart with clean resource release
    """

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self._source: Optional[WebcamSource] = None
        self._running = False
        self._lock = threading.Lock()
        self._frame_callbacks: list[Callable[[Optional[bytes]], None]] = []
        self._last_error: bool = False

    # --- Lifecycle ---

    def start(self) -> str:
        """Start webcam monitoring.

        Returns status string: STARTED, ALREADY_RUNNING, or CAMERA_ERROR.
        """
        with self._lock:
            if self._running and self._source is not None:
                return "ALREADY_RUNNING"

            # Always clean up any existing dormant source before fresh start
            if self._source is not None:
                try:
                    self._source.stop()
                except Exception:
                    pass
                self._source = None

            self._source = WebcamSource(camera_index=self.camera_index)

            def on_frame(frame: Optional[bytes]) -> None:
                with self._lock:
                    for cb in self._frame_callbacks:
                        try:
                            cb(frame)
                        except Exception:
                            pass

            self._source.set_frame_callback(on_frame)
            try:
                self._source.start()
                self._running = True
                return "STARTED"
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"CameraManager failed to start source: {type(e).__name__}: {e}")
                self._running = False
                self._last_error = True
                return "CAMERA_ERROR"

    def stop(self) -> str:
        """Stop monitoring and release camera resource cleanly."""
        with self._lock:
            self._last_error = False
            if not self._running and self._source is None:
                return "STOPPED"

            if self._source is not None:
                try:
                    self._source.stop()
                except Exception:
                    pass
                self._source = None

            self._running = False
            return "STOPPED"

    @property
    def camera_state(self) -> CameraState:
        """Return explicit runtime state."""
        with self._lock:
            if self._source is None:
                return CameraState.STOPPED
            return self._source.camera_state

    @property
    def capture_fps(self) -> float:
        with self._lock:
            if self._source is None:
                return 0.0
            return self._source.capture_fps

    @property
    def last_frame_age_ms(self) -> float:
        with self._lock:
            if self._source is None:
                return 9999.0
            return self._source.last_frame_age_ms

    @property
    def frame_sequence(self) -> int:
        with self._lock:
            if self._source is None:
                return 0
            return self._source.frame_sequence

    def status(self) -> dict:
        """Return truthful camera/monitoring state and diagnostics.

        States: RUNNING, NO_FRAMES, CAMERA_ERROR, RECONNECTING, STOPPED.
        """
        with self._lock:
            if self._source is None:
                st = "CAMERA_ERROR" if getattr(self, "_last_error", False) else "STOPPED"
                cam = "CAMERA_ERROR" if getattr(self, "_last_error", False) else "NOT_CONFIGURED"
                return {
                    "camera": cam,
                    "state": st,
                    "camera_state": "STOPPED",
                    "camera_index": self.camera_index,
                    "backend": "NONE",
                    "frames_received": 0,
                    "capture_fps": 0.0,
                    "last_frame_age_ms": 9999.0,
                    "frame_sequence": 0,
                }

            c_state = self._source.camera_state
            source_health = self._source.health()

            if not self._running:
                state = "CAMERA_ERROR" if source_health == "CAMERA_ERROR" else "STOPPED"
            elif c_state == CameraState.LIVE or source_health == "READY":
                state = "RUNNING"
            elif c_state == CameraState.NO_FRAMES or source_health == "NO_FRAMES":
                state = "NO_FRAMES"
            elif c_state == CameraState.RECONNECTING:
                state = "RECONNECTING"
            elif c_state in (CameraState.CAMERA_BUSY, CameraState.NO_CAMERA, CameraState.ERROR) or source_health == "CAMERA_ERROR":
                state = "CAMERA_ERROR"
            else:
                state = "ERROR"

            return {
                "camera": source_health,
                "state": state,
                "camera_state": c_state.value,
                "camera_index": self._source.camera_index if self._source else self.camera_index,
                "backend": getattr(self._source, "_backend_used", "UNKNOWN"),
                "frames_received": getattr(self._source, "_frames_received", 0),
                "capture_fps": self._source.capture_fps,
                "last_frame_age_ms": round(self._source.last_frame_age_ms, 1),
                "frame_sequence": self._source.frame_sequence,
            }

    # --- Frame observation ---

    def on_frame(self, callback: Callable[[Optional[bytes]], None]) -> None:
        """Register a callback to be called on each new frame."""
        with self._lock:
            self._frame_callbacks.append(callback)

    def get_latest_raw_frame_only(self) -> Optional[np.ndarray]:
        try:
            res = self.get_latest_raw_frame()
            if isinstance(res, tuple) and len(res) == 2:
                return res[1]
        except Exception:
            pass
        return None

    def get_latest_raw_frame(self) -> Tuple[int, Optional[np.ndarray]]:
        """Return monotonic frame_id and newest raw BGR numpy ndarray."""
        with self._lock:
            if self._source is not None and hasattr(self._source, "read_raw"):
                try:
                    res = self._source.read_raw()
                    if res is not None:
                        return res
                except Exception:
                    pass
            return 0, None

    def get_latest_frame(self) -> Optional[bytes]:
        return self.read()

    def read(self) -> Optional[bytes]:
        """Read the latest available JPEG frame."""
        with self._lock:
            if self._source is not None:
                return self._source.read()
            return None


_camera_manager_instance: Optional[CameraManager] = None

def get_camera_manager(camera_index: int = 0) -> CameraManager:
    global _camera_manager_instance
    if _camera_manager_instance is None:
        _camera_manager_instance = CameraManager(camera_index=camera_index)
    return _camera_manager_instance
