"""VisionGuard Workstation Activity Collector.

Collects ONLY derived, privacy-safe human-computer interaction signals:
- keyboard_event_count (count only; zero keylogging, no key names or contents)
- mouse_movement_count
- mouse_click_count
- scroll_count
- mouse_distance (scalar px distance; coordinates discarded immediately)
- last_input_at
- idle_seconds
- foreground_app_changed (HWND handle transition only; zero title or document inspection)
- screen_change_score (downsampled transient diff; pixels immediately discarded)
- screen_activity_level (CHANGING, LOW_CHANGE, STATIC, UNKNOWN)
- last_screen_change_at

STRICT PRIVACY GUARANTEES:
- ABSOLUTELY NEVER stores typed characters, key names, passwords, or clipboard.
- ABSOLUTELY NEVER stores mouse coordinates.
- ABSOLUTELY NEVER inspects window titles, URL strings, or document contents.
- ABSOLUTELY NEVER saves or uploads screenshots or video recordings.
- Downsampled screen thumbnails exist only inside transient memory during calculation.
- Runs in an independent background worker thread; NEVER blocks perception.
"""

from __future__ import annotations

import sys
import time
import math
import threading
from dataclasses import dataclass
from typing import Optional, Dict, Any
import numpy as np


@dataclass
class ActivitySnapshot:
    keyboard_event_count: int
    mouse_movement_count: int
    mouse_click_count: int
    scroll_count: int
    mouse_distance: float
    last_input_at: Optional[float]
    idle_seconds: float
    foreground_app_changed: bool
    screen_change_score: Optional[float]
    screen_activity_level: str = "UNKNOWN"
    last_screen_change_at: Optional[float] = None


class WorkstationActivityCollector:
    """Thread-safe workstation input and screen change activity collector."""

    def __init__(self, sample_interval_sec: float = 0.10):
        self._sample_interval = sample_interval_sec
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Cumulative counters for active session
        self._keyboard_event_count: int = 0
        self._mouse_movement_count: int = 0
        self._mouse_click_count: int = 0
        self._scroll_count: int = 0
        self._mouse_distance: float = 0.0
        self._last_input_at: Optional[float] = None
        self._idle_seconds: float = 0.0
        self._foreground_app_changed: bool = False

        # Privacy-preserving Screen Activity
        self._screen_change_score: Optional[float] = None
        self._screen_activity_level: str = "UNKNOWN"
        self._last_screen_change_at: Optional[float] = None
        self._prev_screen_thumb: Optional[np.ndarray] = None
        self._last_screen_sample_time: float = 0.0

        # Internal tracking variables (transient, never exposed)
        self._last_input_tick: int = 0
        self._last_mouse_x: Optional[int] = None
        self._last_mouse_y: Optional[int] = None
        self._last_lbutton_down: bool = False
        self._last_rbutton_down: bool = False
        self._last_mbutton_down: bool = False
        self._last_hwnd: Optional[int] = None

        # Windows API bindings if on win32
        self._is_windows = sys.platform == "win32"
        self._user32 = None
        self._kernel32 = None
        if self._is_windows:
            try:
                import ctypes
                self._user32 = ctypes.windll.user32
                self._kernel32 = ctypes.windll.kernel32
            except Exception:
                self._is_windows = False

    def start(self) -> None:
        """Start activity collection in background thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._last_input_at = time.time()
            self._idle_seconds = 0.0
            self._foreground_app_changed = False
            self._thread = threading.Thread(
                target=self._worker_loop,
                name="VisionGuard-ActivityCollector",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop background activity collection and discard transient state."""
        with self._lock:
            self._running = False
            self._prev_screen_thumb = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def reset(self) -> None:
        """Reset counters for a new monitoring session."""
        with self._lock:
            self._keyboard_event_count = 0
            self._mouse_movement_count = 0
            self._mouse_click_count = 0
            self._scroll_count = 0
            self._mouse_distance = 0.0
            self._last_input_at = time.time()
            self._idle_seconds = 0.0
            self._foreground_app_changed = False
            self._screen_change_score = None
            self._screen_activity_level = "UNKNOWN"
            self._last_screen_change_at = None
            self._prev_screen_thumb = None
            self._last_mouse_x = None
            self._last_mouse_y = None
            self._last_hwnd = None

    def get_snapshot(self) -> ActivitySnapshot:
        """Return a thread-safe point-in-time snapshot of derived activity metrics."""
        with self._lock:
            snapshot = ActivitySnapshot(
                keyboard_event_count=self._keyboard_event_count,
                mouse_movement_count=self._mouse_movement_count,
                mouse_click_count=self._mouse_click_count,
                scroll_count=self._scroll_count,
                mouse_distance=round(self._mouse_distance, 1),
                last_input_at=self._last_input_at,
                idle_seconds=round(self._idle_seconds, 1),
                foreground_app_changed=self._foreground_app_changed,
                screen_change_score=self._screen_change_score,
                screen_activity_level=self._screen_activity_level,
                last_screen_change_at=self._last_screen_change_at,
            )
            # Reset edge flag after read
            self._foreground_app_changed = False
            return snapshot

    def record_simulated_input(self, event_type: str = "KEYBOARD") -> None:
        """Test and simulation hook to record interaction without OS drivers."""
        with self._lock:
            now = time.time()
            self._last_input_at = now
            self._idle_seconds = 0.0
            if event_type == "KEYBOARD":
                self._keyboard_event_count += 1
            elif event_type == "MOUSE_MOVE":
                self._mouse_movement_count += 1
                self._mouse_distance += 10.0
            elif event_type == "MOUSE_CLICK":
                self._mouse_click_count += 1
            elif event_type == "SCROLL":
                self._scroll_count += 1
            elif event_type == "APP_SWITCH":
                self._foreground_app_changed = True

    def record_simulated_screen_change(self, level: str = "CHANGING", score: float = 15.0) -> None:
        """Test and simulation hook for screen activity changes."""
        with self._lock:
            self._screen_activity_level = level
            self._screen_change_score = score
            if level in ("CHANGING", "LOW_CHANGE"):
                self._last_screen_change_at = time.time()

    def _worker_loop(self) -> None:
        """Lightweight low-overhead sampling loop (~10 Hz)."""
        screen_sample_counter = 0
        while True:
            with self._lock:
                if not self._running:
                    break

            try:
                self._sample_windows_apis()
            except Exception:
                pass

            # Sample screen activity once every 5 ticks (~2 Hz) for minimal CPU impact
            screen_sample_counter += 1
            if screen_sample_counter >= 5:
                screen_sample_counter = 0
                try:
                    self._sample_screen_change()
                except Exception:
                    pass

            time.sleep(self._sample_interval)

    def _sample_windows_apis(self) -> None:
        """Query native Windows input counters with zero sensitive data retention."""
        if not self._is_windows or not self._user32 or not self._kernel32:
            with self._lock:
                if self._last_input_at is not None:
                    self._idle_seconds = time.time() - self._last_input_at
            return

        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("dwTime", wintypes.DWORD),
            ]

        # 1. System Idle Time via GetLastInputInfo
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        input_occurred = False

        if self._user32.GetLastInputInfo(ctypes.byref(lii)):
            curr_tick = int(lii.dwTime)
            uptime_ms = int(self._kernel32.GetTickCount())
            idle_ms = max(0, uptime_ms - curr_tick)
            current_idle_sec = idle_ms / 1000.0

            if self._last_input_tick != 0 and curr_tick != self._last_input_tick:
                input_occurred = True
            self._last_input_tick = curr_tick
        else:
            current_idle_sec = 0.0

        # 2. Mouse Movement via GetCursorPos (coordinates discarded immediately)
        pt = wintypes.POINT()
        mouse_moved = False
        mouse_delta = 0.0

        if self._user32.GetCursorPos(ctypes.byref(pt)):
            cx = int(pt.x)
            cy = int(pt.y)
            if self._last_mouse_x is not None and self._last_mouse_y is not None:
                dx = cx - self._last_mouse_x
                dy = cy - self._last_mouse_y
                dist = math.hypot(dx, dy)
                if dist >= 2.0:
                    mouse_moved = True
                    mouse_delta = dist
            self._last_mouse_x = cx
            self._last_mouse_y = cy

        # 3. Mouse Button State (clicks only; zero coordinates stored)
        l_down = bool(self._user32.GetAsyncKeyState(0x01) & 0x8000)
        r_down = bool(self._user32.GetAsyncKeyState(0x02) & 0x8000)
        m_down = bool(self._user32.GetAsyncKeyState(0x04) & 0x8000)

        click_detected = False
        if l_down and not self._last_lbutton_down:
            click_detected = True
        if r_down and not self._last_rbutton_down:
            click_detected = True
        if m_down and not self._last_mbutton_down:
            click_detected = True

        self._last_lbutton_down = l_down
        self._last_rbutton_down = r_down
        self._last_mbutton_down = m_down

        # 4. Foreground Window Switch (HWND integer check only; NO title inspection)
        hwnd_changed = False
        hwnd = int(self._user32.GetForegroundWindow() or 0)
        if self._last_hwnd is not None and hwnd != self._last_hwnd and hwnd != 0:
            hwnd_changed = True
        self._last_hwnd = hwnd

        # 5. Derived Input Classification
        keyboard_event = False
        if input_occurred:
            if not mouse_moved and not click_detected:
                keyboard_event = True

        # Commit updates to shared state
        with self._lock:
            now = time.time()
            self._idle_seconds = current_idle_sec

            if input_occurred or mouse_moved or click_detected:
                self._last_input_at = now
                self._idle_seconds = 0.0

            if mouse_moved:
                self._mouse_movement_count += 1
                self._mouse_distance += mouse_delta

            if click_detected:
                self._mouse_click_count += 1

            if keyboard_event:
                self._keyboard_event_count += 1

            if hwnd_changed:
                self._foreground_app_changed = True

    def _sample_screen_change(self) -> None:
        """Compute privacy-safe transient downsampled screen difference."""
        try:
            from PIL import ImageGrab
            im = ImageGrab.grab()
            # Downsample to 32x18 grayscale thumbnail immediately
            thumb = np.array(im.resize((32, 18)).convert("L"), dtype=np.uint8)
            del im  # Immediately free full-resolution screen buffer

            with self._lock:
                now = time.time()
                if self._prev_screen_thumb is not None:
                    diff = float(np.mean(np.abs(thumb.astype(float) - self._prev_screen_thumb.astype(float))))
                    self._screen_change_score = round(diff, 2)
                    if diff >= 10.0:
                        self._screen_activity_level = "CHANGING"
                        self._last_screen_change_at = now
                    elif diff >= 2.5:
                        self._screen_activity_level = "LOW_CHANGE"
                        self._last_screen_change_at = now
                    else:
                        self._screen_activity_level = "STATIC"
                else:
                    self._screen_change_score = 0.0
                    self._screen_activity_level = "STATIC"

                self._prev_screen_thumb = thumb
        except Exception:
            with self._lock:
                if self._screen_activity_level is None or self._screen_activity_level == "UNKNOWN":
                    self._screen_activity_level = "UNKNOWN"


_collector_instance: Optional[WorkstationActivityCollector] = None

def get_activity_collector() -> WorkstationActivityCollector:
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = WorkstationActivityCollector()
    return _collector_instance
