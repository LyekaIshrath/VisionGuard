from __future__ import annotations

import platform
import threading
import time
from typing import Optional, Callable, Tuple, Union

import cv2
import numpy as np

from app.camera.source import CameraSource
from app.human_state.models import HumanState


class WebcamSource:
    """Real webcam source using OpenCV VideoCapture.

    Implements the CameraSource protocol.
    ONE dedicated capture loop owns VideoCapture.
    Frame consumers read the latest frame from a thread-safe buffer.
    """

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self._capture: Optional[cv2.VideoCapture] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame: Optional[bytes] = None
        self._latest_raw_frame: Optional[np.ndarray] = None
        self._latest_frame_id: int = 0
        self._frame_lock = threading.Lock()
        self._health_status = "NOT_CONFIGURED"
        self._frame_callback: Optional[Callable[[Optional[bytes]], None]] = None
        self._backend_used: str = "UNKNOWN"
        self._frame_shape: Optional[Tuple[int, ...]] = None
        self._frames_received: int = 0

    # --- Camera Opening Logic ---

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        """Attempt to open camera using platform-appropriate backends and select the first working camera."""
        is_windows = platform.system() == "Windows"

        # On Windows, CAP_DSHOW reliably accesses webcams without MSMF stream type errors (-1072875772)
        backends = [
            ("CAP_DSHOW", cv2.CAP_DSHOW),
            ("CAP_ANY", cv2.CAP_ANY),
        ] if is_windows else [("CAP_ANY", cv2.CAP_ANY)]

        # Candidate camera indices: requested index first, then alternate (e.g. 0, 1)
        indices = [self.camera_index]
        for alt in (0, 1, 2):
            if alt not in indices:
                indices.append(alt)

        for idx in indices:
            for b_name, b_val in backends:
                try:
                    cap = cv2.VideoCapture(idx, b_val)
                    if cap.isOpened():
                        # Set optimal preview / capture properties
                        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        cap.set(cv2.CAP_PROP_FPS, 30)
                        # Verify we can actually read a valid frame!
                        ret, test_frame = cap.read()
                        if ret and test_frame is not None and hasattr(test_frame, 'shape') and len(test_frame.shape) == 3:
                            self.camera_index = idx
                            self._backend_used = b_name
                            self._frame_shape = test_frame.shape
                            return cap
                    cap.release()
                except Exception:
                    pass

        return None

    # --- CameraSource Protocol ---

    def start(self) -> None:
        """Start the webcam capture.

        Opens the camera, verifies frames are actually being delivered,
        and begins the read loop in a background thread.
        """
        if self._running:
            return

        self._capture = self._open_capture()
        if self._capture is None or not self._capture.isOpened():
            self._health_status = "CAMERA_ERROR"
            raise RuntimeError(
                f"Camera index {self.camera_index} could not be opened or failed to provide frames"
            )

        # Discard first few frames to allow auto-exposure to settle
        for _ in range(5):
            self._capture.read()

        self._running = True
        self._health_status = "READY"
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def read_raw(self) -> Tuple[int, Optional[np.ndarray]]:
        """Return monotonic frame ID and raw BGR numpy frame without JPEG encoding."""
        with self._frame_lock:
            return self._latest_frame_id, self._latest_raw_frame

    def read(self) -> Optional[bytes]:
        """Read the latest available frame as JPEG bytes (CameraSource protocol)."""
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
            if isinstance(frame_data, bytes):
                self._frame = frame_data
                nparr = np.frombuffer(frame_data, np.uint8)
                self._latest_raw_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            else:
                self._latest_raw_frame = frame_data
                self._frame = None

    def stop(self) -> None:
        """Stop the webcam capture and release resources."""
        self._running = False
        if self._thread is not None:
            try:
                self._thread.join(timeout=3.0)
            except Exception:
                pass
            self._thread = None

        if self._capture is not None:
            try:
                self._capture.release()
            except Exception:
                pass
            self._capture = None

        self._health_status = "NOT_CONFIGURED"

    def set_frame_callback(self, callback: Callable[[Optional[bytes]], None]) -> None:
        """Register a callback to be called with each new frame."""
        self._frame_callback = callback

    def health(self) -> str:
        """Return truthful health status: READY, NO_FRAMES, CAMERA_ERROR, or NOT_CONFIGURED."""
        if self._health_status == "CAMERA_ERROR":
            return "CAMERA_ERROR"
        if not self._running or self._capture is None:
            return "NOT_CONFIGURED"
        return self._health_status

    # --- Internal read loop ---

    def _read_loop(self) -> None:
        """Background thread that continuously reads frames from VideoCapture."""
        consecutive_failures = 0

        while self._running:
            try:
                ret, frame = self._capture.read()
                if ret and frame is not None:
                    consecutive_failures = 0
                    self._frames_received += 1
                    self._health_status = "READY"

                    # Publish newest raw frame into single-frame slot (dropping old frames)
                    with self._frame_lock:
                        self._latest_frame_id += 1
                        self._latest_raw_frame = frame
                        self._frame = None

                    # Fire callback if registered (non-blocking notification)
                    if self._frame_callback is not None:
                        try:
                            self._frame_callback(frame)
                        except Exception:
                            pass
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= 30:  # ~1 second of failed reads
                        self._health_status = "NO_FRAMES"
                    time.sleep(0.01)

            except cv2.error:
                consecutive_failures += 1
                if consecutive_failures >= 30:
                    self._health_status = "CAMERA_ERROR"
                    break
                time.sleep(0.01)
            except Exception:
                consecutive_failures += 1
                if consecutive_failures >= 30:
                    self._health_status = "CAMERA_ERROR"
                    break
                time.sleep(0.01)

        if self._running:
            self._health_status = "CAMERA_ERROR"
            self._running = False


