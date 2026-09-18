from __future__ import annotations

import threading
from typing import Optional, Callable, Tuple
import numpy as np

from app.camera.source import CameraSource
from app.camera.webcam_source import WebcamSource
from app.human_state.models import HumanState


class CameraManager:
    """Manages a single WebcamSource instance lifecycle.

    Controls camera ownership - only one manager per camera index.
    Provides start/stop/status for monitoring.
    Thread-safe: background loop owns frame buffer; readers copy latest frame.
    """

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self._source: Optional[WebcamSource] = None
        self._running = False
        self._lock = threading.Lock()
        self._frame_callbacks: list[Callable[[Optional[bytes]], None]] = []

    # --- Lifecycle ---

    def start(self) -> str:
        """Start the webcam monitoring.

        Returns status string: STARTED, ALREADY_RUNNING, or CAMERA_ERROR.
        """
        with self._lock:
            if self._running:
                return "ALREADY_RUNNING"

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
            except Exception:
                self._running = False
                return "CAMERA_ERROR"

    def stop(self) -> str:
        """Stop monitoring and release the camera."""
        with self._lock:
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

    def status(self) -> dict:
        """Return truthful camera/monitoring state.

        States: RUNNING, NO_FRAMES, CAMERA_ERROR, ERROR, STOPPED.
        """
        with self._lock:
            if self._source is None:
                return {
                    "camera": "NOT_CONFIGURED",
                    "state": "STOPPED",
                    "camera_index": self.camera_index,
                    "backend": "NONE",
                    "frames_received": 0,
                }

            source_health = self._source.health()
            if not self._running:
                state = "CAMERA_ERROR" if source_health == "CAMERA_ERROR" else "STOPPED"
            elif source_health == "READY":
                state = "RUNNING"
            elif source_health == "NO_FRAMES":
                state = "NO_FRAMES"
            elif source_health == "CAMERA_ERROR":
                state = "CAMERA_ERROR"
            else:
                state = "ERROR"

            return {
                "camera": source_health,
                "state": state,
                "camera_index": self._source.camera_index if self._source else self.camera_index,
                "backend": getattr(self._source, "_backend_used", "UNKNOWN"),
                "frames_received": getattr(self._source, "_frames_received", 0),
            }

    # --- Frame observation ---

    def on_frame(self, callback: Callable[[Optional[bytes]], None]) -> None:
        """Register a callback to be called on each new frame."""
        with self._lock:
            self._frame_callbacks.append(callback)

    def get_latest_raw_frame(self) -> Tuple[int, Optional[np.ndarray]]:
        """Return monotonic frame_id and newest raw BGR numpy ndarray."""
        with self._lock:
            if self._source is not None and hasattr(self._source, "read_raw"):
                try:
                    res = self._source.read_raw()
                    if isinstance(res, tuple) and len(res) == 2:
                        return res
                except Exception:
                    pass
            return 0, None

    def get_latest_raw_frame_only(self) -> Optional[np.ndarray]:
        """Return newest raw BGR numpy ndarray directly or None."""
        try:
            res = self.get_latest_raw_frame()
            if isinstance(res, tuple) and len(res) == 2:
                return res[1]
        except Exception:
            pass
        return None

    def get_latest_frame(self) -> Optional[bytes]:
        """Return the latest captured frame bytes, or None."""
        with self._lock:
            if self._source is not None:
                return self._source.read()
            return None


# Module-level singleton camera manager
_camera_manager: Optional[CameraManager] = None


def get_camera_manager(camera_index: int = 0) -> CameraManager:
    """Get or create the module-level camera manager instance."""
    global _camera_manager
    if _camera_manager is None or _camera_manager.camera_index != camera_index:
        _camera_manager = CameraManager(camera_index=camera_index)
    return _camera_manager
