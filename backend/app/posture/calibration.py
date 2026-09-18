"""Personal Posture Calibration Service for VisionGuard.

Manages personalized baseline collection, sample validation, stability checking,
and robust aggregation (median) to produce an immutable PostureBaseline for V1.
"""

from __future__ import annotations

import statistics
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from app.posture.geometry import BodyGeometry


class CalibrationState(str, Enum):
    IDLE = "IDLE"
    COLLECTING = "COLLECTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PostureBaseline:
    """Immutable calibrated baseline for an individual user."""
    shoulder_width: float
    torso_length: float
    shoulder_tilt: float
    head_lateral_displacement: float
    torso_lateral_displacement: float
    head_shoulder_vertical_ratio: float
    slouch_proxy: float
    forward_lean_proxy: float
    confidence: float
    quality: str
    sample_count: int
    has_hips: bool = True


class PostureCalibrationService:
    """Service to capture and calculate personalized posture baseline."""

    # Default parameters: ~3-5 seconds of samples at typical 10-20 FPS
    DEFAULT_REQUIRED_SAMPLES: int = 40
    # Stability thresholds (CV or std dev)
    MAX_CV_SHOULDER_WIDTH: float = 0.15
    MAX_CV_HEAD_VERTICAL: float = 0.15
    MAX_STD_SHOULDER_TILT: float = 0.08
    MAX_STD_HEAD_LATERAL: float = 0.08
    MAX_CONSECUTIVE_DROPPED: int = 60

    def __init__(self, required_samples: int = DEFAULT_REQUIRED_SAMPLES):
        self._required_samples = required_samples
        self._state = CalibrationState.IDLE
        self._samples: List[BodyGeometry] = []
        self._baseline: Optional[PostureBaseline] = None
        self._failure_reason: Optional[str] = None
        self._consecutive_dropped: int = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CalibrationState:
        with self._lock:
            return self._state

    @property
    def baseline(self) -> Optional[PostureBaseline]:
        with self._lock:
            return self._baseline

    @property
    def is_calibrated(self) -> bool:
        with self._lock:
            return self._state == CalibrationState.COMPLETED and self._baseline is not None

    def start_calibration(self) -> Dict[str, Any]:
        """Begin collecting calibration samples."""
        with self._lock:
            self._samples.clear()
            self._baseline = None
            self._failure_reason = None
            self._consecutive_dropped = 0
            self._state = CalibrationState.COLLECTING
            return self._get_status_locked()

    def reset_calibration(self) -> Dict[str, Any]:
        """Reset calibration back to IDLE, completely invalidating baseline."""
        with self._lock:
            self._samples.clear()
            self._baseline = None
            self._failure_reason = None
            self._consecutive_dropped = 0
            self._state = CalibrationState.IDLE
            return self._get_status_locked()

    def add_sample(self, geometry: Optional[BodyGeometry]) -> CalibrationState:
        """Process a frame's geometry during calibration.

        Must require BOTH sufficient valid samples AND acceptable stability.
        Elapsed time alone never completes calibration.
        """
        with self._lock:
            if self._state != CalibrationState.COLLECTING:
                return self._state

            if geometry is None or geometry.confidence < 0.5:
                self._consecutive_dropped += 1
                if self._consecutive_dropped >= self.MAX_CONSECUTIVE_DROPPED:
                    self._state = CalibrationState.FAILED
                    self._failure_reason = "POSE_LOST: Pose lost or person moved out of camera view during calibration."
                return self._state

            # Valid sample received
            self._consecutive_dropped = 0
            self._samples.append(geometry)

            # Check if required sample count reached
            if len(self._samples) >= self._required_samples:
                self._evaluate_and_finalize_locked()

            return self._state

    def _evaluate_and_finalize_locked(self) -> None:
        """Evaluate stability of collected samples and finalize baseline or fail."""
        if len(self._samples) < self._required_samples:
            return

        widths = [s.shoulder_width for s in self._samples]
        verts = [s.head_shoulder_vertical_ratio for s in self._samples]
        tilts = [s.shoulder_tilt for s in self._samples]
        lats = [s.head_lateral_displacement for s in self._samples]

        try:
            mean_w = statistics.mean(widths)
            std_w = statistics.stdev(widths) if len(widths) > 1 else 0.0
            cv_w = std_w / mean_w if mean_w > 1e-6 else 1.0

            mean_v = statistics.mean(verts)
            std_v = statistics.stdev(verts) if len(verts) > 1 else 0.0
            cv_v = std_v / mean_v if mean_v > 1e-6 else 1.0

            std_tilt = statistics.stdev(tilts) if len(tilts) > 1 else 0.0
            std_lat = statistics.stdev(lats) if len(lats) > 1 else 0.0
        except Exception as e:
            self._state = CalibrationState.FAILED
            self._failure_reason = f"CALCULATION_ERROR: Could not verify stability: {e}"
            return

        # Stability rejection checks
        if (
            cv_w > self.MAX_CV_SHOULDER_WIDTH
            or cv_v > self.MAX_CV_HEAD_VERTICAL
            or std_tilt > self.MAX_STD_SHOULDER_TILT
            or std_lat > self.MAX_STD_HEAD_LATERAL
        ):
            self._state = CalibrationState.FAILED
            self._failure_reason = (
                "EXCESSIVE_MOVEMENT: Posture was too unstable during calibration. "
                "Please sit upright and still, then try again."
            )
            return

        # Robust aggregation: MEDIAN across samples
        median_width = statistics.median(widths)
        median_torso = statistics.median([s.torso_length for s in self._samples])
        median_tilt = statistics.median(tilts)
        median_head_lat = statistics.median(lats)
        median_torso_lat = statistics.median([s.torso_lateral_displacement for s in self._samples])
        median_vert = statistics.median(verts)
        median_slouch = statistics.median([s.slouch_proxy for s in self._samples])
        median_fwd = statistics.median([s.forward_lean_proxy for s in self._samples])
        avg_conf = statistics.mean([s.confidence for s in self._samples])

        # Quality rating
        avg_cv = (cv_w + cv_v + (std_tilt * 2.0) + (std_lat * 2.0)) / 4.0
        if avg_cv < 0.05:
            quality = "EXCELLENT"
        elif avg_cv < 0.10:
            quality = "GOOD"
        else:
            quality = "ACCEPTABLE"

        has_hips = any(s.has_hips for s in self._samples)

        self._baseline = PostureBaseline(
            shoulder_width=round(median_width, 5),
            torso_length=round(median_torso, 5),
            shoulder_tilt=round(median_tilt, 5),
            head_lateral_displacement=round(median_head_lat, 5),
            torso_lateral_displacement=round(median_torso_lat, 5),
            head_shoulder_vertical_ratio=round(median_vert, 5),
            slouch_proxy=round(median_slouch, 5),
            forward_lean_proxy=round(median_fwd, 5),
            confidence=round(avg_conf, 4),
            quality=quality,
            sample_count=len(self._samples),
            has_hips=has_hips,
        )
        self._state = CalibrationState.COMPLETED
        self._failure_reason = None

    def get_status(self) -> Dict[str, Any]:
        """Return truthful status for calibration API and consumers."""
        with self._lock:
            return self._get_status_locked()

    def _get_status_locked(self) -> Dict[str, Any]:
        valid_count = len(self._samples)
        req_count = self._required_samples
        progress = min(1.0, round(valid_count / req_count, 3)) if req_count > 0 else 0.0

        return {
            "state": self._state.value,
            "progress": progress,
            "valid_samples": valid_count,
            "required_samples": req_count,
            "quality": self._baseline.quality if self._baseline else None,
            "failure_reason": self._failure_reason,
        }
