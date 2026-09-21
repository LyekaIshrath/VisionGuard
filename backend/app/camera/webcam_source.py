from __future__ import annotations

import logging
import platform
import threading
import time
from enum import Enum
from typing import Optional, Callable, Tuple, Union

import cv2
import numpy as np

from app.camera.source import CameraSource
from app.human_state.models import HumanState

logger = logging.getLogger(__name__)


class CameraState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    LIVE = "LIVE"
    NO_CAMERA = "NO_CAMERA"
    CAMERA_BUSY = "CAMERA_BUSY"
    NO_FRAMES = "NO_FRAMES"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"


class WebcamSource:
    """Real webcam source using OpenCV VideoCapture.

    Implements the CameraSource protocol.
    ONE dedicated capture loop owns VideoCapture.
    Frame consumers read the latest frame from a thread-safe buffer.

    Strict Invariants:
    - Exactly 1 cv2.VideoCapture instance at any time.
    - Explicit runtime states: STOPPED, STARTING, LIVE, NO_CAMERA, CAMERA_BUSY, NO_FRAMES, RECONNECTING, ERROR.
    - Automatic stale-frame detection (> 1500 ms) and controlled auto-reconnect.
    - Safe start / stop / restart lifecycle with zero resource leaks.
    """

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self._capture: Optional[cv2.VideoCapture] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame: Optional[bytes] = None
        self._latest_raw_frame: Optional[np.ndarray] = None
        self._latest_frame_id: int = 0
        self._last_frame_timestamp: float = 0.0
        self._frame_lock = threading.Lock()
        self._capture_lock = threading.Lock()

        # Explicit Camera State
        self._state: CameraState = CameraState.STOPPED
        self._health_status: str = "NOT_CONFIGURED"
        self._frame_callback: Optional[Callable[[Optional[bytes]], None]] = None
        self._backend_used: str = "UNKNOWN"
        self._frame_shape: Optional[Tuple[int, ...]] = None
        self._frames_received: int = 0

        # Rolling FPS metrics
        self._fps_window_start: Optional[float] = None
        self._fps_window_count: int = 0
        self._measured_capture_fps: float = 0.0
        self._consecutive_read_failures: int = 0
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = 5

    # --- Camera Opening Logic ---

    def _probe_and_open(self) -> Tuple[CameraState, Optional[cv2.VideoCapture]]:
        """Attempt to open camera with explicit state diagnostics."""
        is_windows = platform.system() == "Windows"
        backends = [
            ("CAP_MSMF", cv2.CAP_MSMF),
            ("CAP_ANY", cv2.CAP_ANY),
            ("CAP_DSHOW", cv2.CAP_DSHOW),
        ] if is_windows else [("CAP_ANY", cv2.CAP_ANY)]

        indices = [self.camera_index]
        for alt in (0, 1, 2):
            if alt not in indices:
                indices.append(alt)

        any_device_exists = False
        device_busy = False

        for idx in indices:
            for b_name, b_val in backends:
                cap = None
                try:
                    logger.info(f"Probing camera idx={idx} with backend={b_name}...")
                    cap = cv2.VideoCapture(idx, b_val)
                    if cap.isOpened():
                        any_device_exists = True
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        cap.set(cv2.CAP_PROP_FPS, 30)

                        # Test-read frame to ensure driver isn't blocked / busy
                        ret, test_frame = cap.read()
                        if ret and test_frame is not None and hasattr(test_frame, 'shape') and len(test_frame.shape) == 3:
                            self.camera_index = idx
                            self._backend_used = b_name
                            self._frame_shape = test_frame.shape
                            logger.info(f"Successfully opened camera idx={idx} backend={b_name} shape={test_frame.shape}")
                            return CameraState.LIVE, cap
                        else:
                            logger.warning(f"Camera opened idx={idx} backend={b_name} but initial read failed (busy/locked)")
                            device_busy = True
                    if cap is not None:
                        cap.release()
                except Exception as e:
                    logger.error(f"Error opening camera idx={idx} backend={b_name}: {type(e).__name__}: {e}")
                    if cap is not None:
                        try:
                            cap.release()
                        except Exception:
                            pass

        if device_busy:
            return CameraState.CAMERA_BUSY, None
        if not any_device_exists:
            return CameraState.NO_CAMERA, None
        return CameraState.ERROR, None

    # --- CameraSource Protocol ---

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        """Open capture device using probe logic (non-recursive)."""
        state, cap = self._probe_and_open()
        if cap is None:
            self._state = state
        return cap

    def start(self) -> None:
        """Start the webcam capture loop. Transitions: STOPPED -> STARTING -> LIVE."""
        with self._capture_lock:
            if self._running:
                return

            self._state = CameraState.STARTING
            logger.info(f"WebcamSource.start called (camera_index={self.camera_index})")

            cap = self._open_capture()
            if cap is None or not cap.isOpened():
                if self._state == CameraState.STARTING:
                    self._state = CameraState.NO_CAMERA if self.camera_index > 0 else CameraState.ERROR
                self._health_status = "CAMERA_ERROR"
                raise RuntimeError(
                    f"Camera index {self.camera_index} failed to open (State: {self._state.value})"
                )

            # Discard first warmup frame and read at least ONE authoritative first frame
            warmup_ret, first_frame = cap.read()
            if not warmup_ret or first_frame is None or not hasattr(first_frame, 'shape'):
                self._state = CameraState.NO_FRAMES
                self._health_status = "NO_FRAMES"
                cap.release()
                raise RuntimeError(
                    f"Camera index {self.camera_index} opened but failed to yield initial frame"
                )

            now_ts = time.monotonic()
            self._capture = cap
            self._running = True

            # Register first valid frame before marking LIVE
            with self._frame_lock:
                self._latest_frame_id = 1
                self._latest_raw_frame = first_frame
                self._frame = None

            self._frames_received = 1
            self._last_frame_timestamp = now_ts
            self._state = CameraState.LIVE
            self._health_status = "READY"
            self._consecutive_read_failures = 0
            self._reconnect_attempts = 0

            self._thread = threading.Thread(
                target=self._read_loop,
                name="VisionGuard-WebcamAcquisition",
                daemon=True,
            )
            self._thread.start()
            logger.info(f"WebcamSource acquisition thread started (State: {self._state.value})")

    def read_raw(self) -> Tuple[int, Optional[np.ndarray]]:
        """Return monotonic frame ID and raw BGR numpy frame."""
        with self._frame_lock:
            return self._latest_frame_id, self._latest_raw_frame

    def read(self) -> Optional[bytes]:
        """Read the latest available frame as JPEG bytes."""
        with self._frame_lock:
            if self._frame is not None:
                return self._frame
            if self._latest_raw_frame is not None:
                small = cv2.resize(self._latest_raw_frame, (640, 480))
                ok, buf = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ok:
                    self._frame = buf.tobytes()
                    return self._frame
            return None

    def write_frame(self, frame_data: Union[bytes, np.ndarray]) -> None:
        """Store latest frame accepting either raw numpy array or JPEG bytes."""
        with self._frame_lock:
            self._latest_frame_id += 1
            self._last_frame_timestamp = time.monotonic()
            if isinstance(frame_data, bytes):
                self._frame = frame_data
                nparr = np.frombuffer(frame_data, np.uint8)
                self._latest_raw_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            else:
                self._latest_raw_frame = frame_data
                self._frame = None

    def stop(self) -> None:
        """Stop capture loop and release camera resource immediately."""
        logger.info("WebcamSource.stop requested")
        self._running = False
        if self._thread is not None:
            try:
                self._thread.join(timeout=2.0)
            except Exception:
                pass
            self._thread = None

        with self._capture_lock:
            if self._capture is not None:
                try:
                    self._capture.release()
                except Exception:
                    pass
                self._capture = None

        with self._frame_lock:
            self._latest_raw_frame = None
            self._frame = None

        self._state = CameraState.STOPPED
        self._health_status = "NOT_CONFIGURED"
        logger.info("WebcamSource stopped cleanly and resource released")

    def set_frame_callback(self, callback: Callable[[Optional[bytes]], None]) -> None:
        """Register frame callback."""
        self._frame_callback = callback

    @property
    def camera_state(self) -> CameraState:
        return self._state

    @property
    def capture_fps(self) -> float:
        return self._measured_capture_fps

    @property
    def last_frame_age_ms(self) -> float:
        if self._last_frame_timestamp <= 0.0:
            return 9999.0
        return max(0.0, (time.monotonic() - self._last_frame_timestamp) * 1000.0)

    @property
    def frame_sequence(self) -> int:
        return self._latest_frame_id

    def health(self) -> str:
        """Return truthful health status string."""
        if self._health_status == "CAMERA_ERROR" or self._state in (CameraState.CAMERA_BUSY, CameraState.NO_CAMERA, CameraState.ERROR):
            return "CAMERA_ERROR"
        if self._state == CameraState.LIVE:
            return "READY"
        if self._state == CameraState.NO_FRAMES:
            return "NO_FRAMES"
        if self._state == CameraState.RECONNECTING:
            return "RECONNECTING"
        if not self._running or self._capture is None:
            return "NOT_CONFIGURED"
        return self._health_status

    # --- Internal Read Loop & Reconnect Recovery ---

    def _attempt_reconnect(self) -> bool:
        """Controlled recovery loop when frames stop arriving."""
        self._state = CameraState.RECONNECTING
        self._health_status = "RECONNECTING"
        self._reconnect_attempts += 1
        logger.warning(f"Camera attempting reconnect #{self._reconnect_attempts}...")

        with self._capture_lock:
            if self._capture is not None:
                try:
                    self._capture.release()
                except Exception:
                    pass
                self._capture = None

            time.sleep(0.5)
            state, new_cap = self._probe_and_open()
            if new_cap is not None and new_cap.isOpened():
                self._capture = new_cap
                self._state = CameraState.LIVE
                self._health_status = "READY"
                self._last_frame_timestamp = time.monotonic()
                self._consecutive_read_failures = 0
                logger.info("Camera successfully reconnected and live")
                return True
            else:
                self._state = state
                if self._reconnect_attempts >= self._max_reconnect_attempts:
                    self._health_status = "CAMERA_ERROR"
                logger.error(f"Camera reconnect failed (state: {state.value})")
                return False

    def _read_loop(self) -> None:
        """Background thread continuously acquiring frames from VideoCapture."""
        while self._running:
            cap = self._capture
            if cap is None or not cap.isOpened():
                if not self._attempt_reconnect():
                    time.sleep(0.5)
                    continue

            try:
                ret, frame = self._capture.read()
                now_ts = time.monotonic()

                if ret and frame is not None and hasattr(frame, "shape") and frame.size > 0:
                    self._consecutive_read_failures = 0
                    self._frames_received += 1
                    self._state = CameraState.LIVE
                    self._health_status = "READY"
                    self._last_frame_timestamp = now_ts

                    # Rolling FPS measurement
                    self._fps_window_count += 1
                    if self._fps_window_start is None:
                        self._fps_window_start = now_ts
                    elif now_ts - self._fps_window_start >= 1.0:
                        elapsed = now_ts - self._fps_window_start
                        self._measured_capture_fps = round(self._fps_window_count / elapsed, 1)
                        self._fps_window_count = 0
                        self._fps_window_start = now_ts

                    with self._frame_lock:
                        self._latest_frame_id += 1
                        self._latest_raw_frame = frame
                        self._frame = None

                    if self._frame_callback is not None:
                        try:
                            self._frame_callback(frame)
                        except Exception:
                            pass
                else:
                    self._consecutive_read_failures += 1
                    # Only trigger stale-frame recovery if camera was already LIVE and producing frames
                    if self._state == CameraState.LIVE and self._last_frame_timestamp > 0:
                        age_ms = (now_ts - self._last_frame_timestamp) * 1000.0
                        if age_ms >= 1500.0 or self._consecutive_read_failures >= 45:
                            logger.warning(f"Stale frame detected (age={age_ms:.1f}ms, failures={self._consecutive_read_failures})")
                            self._state = CameraState.NO_FRAMES
                            self._health_status = "NO_FRAMES"
                            self._attempt_reconnect()
                    elif self._state == CameraState.STARTING:
                        # Allow reasonable hardware initialization window
                        pass

                    time.sleep(0.01)

            except Exception as e:
                logger.error(f"Exception in webcam read loop: {type(e).__name__}: {e}")
                self._consecutive_read_failures += 1
                if self._state == CameraState.LIVE and self._consecutive_read_failures >= 30:
                    self._attempt_reconnect()
                time.sleep(0.01)

        # Cleanup on thread exit
        with self._capture_lock:
            if self._capture is not None:
                try:
                    self._capture.release()
                except Exception:
                    pass
                self._capture = None
