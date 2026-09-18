"""Alertness Calibration Service.

Collects a personalized open-eye wakefulness baseline over 3–5 seconds.
Robustly filters out natural blinks during calibration to avoid corrupting baseline.
Derives personalized thresholds for eye closure, yawn, and head drop.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Any

from app.alertness.config import AlertnessConfig, DEFAULT_CONFIG
from app.alertness.geometry import FaceGeometry


class CalibrationState(str, Enum):
    IDLE = "IDLE"
    COLLECTING = "COLLECTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class AlertnessBaseline:
    open_eye_ear: float
    closed_eye_threshold: float
    mouth_mor: float
    yawn_threshold: float
    head_pitch_ratio: float
    head_nod_threshold: float
    samples_count: int
    quality: str


class AlertnessCalibrationService:
    """Manages the in-memory personal alertness calibration lifecycle."""

    def __init__(self, config: AlertnessConfig = DEFAULT_CONFIG):
        self._config = config
        self._state = CalibrationState.IDLE
        self._samples: List[FaceGeometry] = []
        self._rejected_invalid_count: int = 0
        self._baseline: Optional[AlertnessBaseline] = None
        self._failure_reason: Optional[str] = None
        self._quality: Optional[str] = None

    @property
    def state(self) -> CalibrationState:
        return self._state

    @property
    def is_calibrated(self) -> bool:
        return self._state == CalibrationState.COMPLETED and self._baseline is not None

    @property
    def baseline(self) -> Optional[AlertnessBaseline]:
        return self._baseline

    def start_calibration(self) -> Dict[str, Any]:
        """Begin calibration sample collection."""
        self._state = CalibrationState.COLLECTING
        self._samples.clear()
        self._rejected_invalid_count = 0
        self._baseline = None
        self._failure_reason = None
        self._quality = None
        return self.get_status()

    def reset_calibration(self) -> None:
        """Reset calibration and invalidate any baseline."""
        self._state = CalibrationState.IDLE
        self._samples.clear()
        self._rejected_invalid_count = 0
        self._baseline = None
        self._failure_reason = None
        self._quality = None

    def add_sample(self, geometry: Optional[FaceGeometry]) -> CalibrationState:
        """Add a frame's FaceGeometry sample during COLLECTING state."""
        if self._state != CalibrationState.COLLECTING:
            return self._state

        if geometry is None or not geometry.is_valid or geometry.combined_ear is None:
            self._rejected_invalid_count += 1
            if self._rejected_invalid_count >= self._config.calibration_required_samples * 2:
                self._state = CalibrationState.FAILED
                self._failure_reason = "Face lost or landmarks unstable for too many consecutive frames."
            return self._state

        self._samples.append(geometry)

        if len(self._samples) >= self._config.calibration_required_samples:
            self._finalize_calibration()

        return self._state

    def _finalize_calibration(self) -> None:
        """Process collected samples with robust outlier rejection."""
        if len(self._samples) < self._config.calibration_required_samples:
            self._state = CalibrationState.FAILED
            self._failure_reason = "Insufficient valid facial samples collected."
            return

        ear_vals = [s.combined_ear for s in self._samples if s.combined_ear is not None]
        mor_vals = [s.mouth_ratio for s in self._samples if s.mouth_ratio is not None]
        pitch_vals = [s.head_pitch_ratio for s in self._samples if s.head_pitch_ratio is not None]

        if not ear_vals:
            self._state = CalibrationState.FAILED
            self._failure_reason = "No valid eye openness samples found."
            return

        # --- Filter out blinks during calibration ---
        # Sort EAR values: natural blinks appear in the lowest percentile
        ear_sorted = sorted(ear_vals)
        discard_count = int(len(ear_sorted) * (self._config.calibration_blink_discard_percentile / 100.0))
        # Keep upper (open-eye) samples
        open_ear_samples = ear_sorted[discard_count:] if discard_count < len(ear_sorted) else ear_sorted

        if not open_ear_samples:
            self._state = CalibrationState.FAILED
            self._failure_reason = "Could not isolate stable open-eye samples."
            return

        # Median open-eye EAR
        mid = len(open_ear_samples) // 2
        if len(open_ear_samples) % 2 == 1:
            median_ear = open_ear_samples[mid]
        else:
            median_ear = (open_ear_samples[mid - 1] + open_ear_samples[mid]) / 2.0

        # Stability evaluation: standard deviation and coefficient of variation (CV)
        mean_ear = sum(open_ear_samples) / len(open_ear_samples)
        variance = sum((x - mean_ear) ** 2 for x in open_ear_samples) / len(open_ear_samples)
        std_dev = math.sqrt(variance)
        cv = std_dev / mean_ear if mean_ear > 1e-4 else 1.0

        if cv > self._config.calibration_max_ear_cv:
            self._state = CalibrationState.FAILED
            self._failure_reason = f"Eye openness too unstable during calibration (CV={cv:.2f} > {self._config.calibration_max_ear_cv:.2f})."
            return

        # Quality determination
        if cv < 0.10:
            quality = "EXCELLENT"
        elif cv < 0.20:
            quality = "GOOD"
        else:
            quality = "ACCEPTABLE"

        # Mouth baseline (median)
        if mor_vals:
            mor_sorted = sorted(mor_vals)
            mid_mor = len(mor_sorted) // 2
            median_mor = mor_sorted[mid_mor]
        else:
            median_mor = 0.20

        # Head pitch baseline (median)
        if pitch_vals:
            pitch_sorted = sorted(pitch_vals)
            mid_pitch = len(pitch_sorted) // 2
            median_pitch = pitch_sorted[mid_pitch]
        else:
            median_pitch = 0.50

        # Derive personalized thresholds
        closed_threshold = round(median_ear * self._config.ear_closure_ratio, 4)
        yawn_threshold = round(max(median_mor * self._config.mor_yawn_multiplier, self._config.mor_yawn_min_absolute), 4)
        head_nod_threshold = round(median_pitch + self._config.head_nod_pitch_offset, 4)

        self._baseline = AlertnessBaseline(
            open_eye_ear=round(median_ear, 4),
            closed_eye_threshold=closed_threshold,
            mouth_mor=round(median_mor, 4),
            yawn_threshold=yawn_threshold,
            head_pitch_ratio=round(median_pitch, 4),
            head_nod_threshold=head_nod_threshold,
            samples_count=len(self._samples),
            quality=quality,
        )
        self._quality = quality
        self._state = CalibrationState.COMPLETED

    def get_status(self) -> Dict[str, Any]:
        """Return truthful calibration progress and baseline metadata."""
        progress = min(1.0, len(self._samples) / float(self._config.calibration_required_samples))
        res = {
            "state": self._state.value,
            "progress": round(progress, 2),
            "valid_samples": len(self._samples),
            "required_samples": self._config.calibration_required_samples,
            "quality": self._quality,
            "failure_reason": self._failure_reason,
        }
        if self._baseline is not None:
            res["baseline"] = {
                "open_eye_ear": self._baseline.open_eye_ear,
                "closed_eye_threshold": self._baseline.closed_eye_threshold,
                "mouth_mor": self._baseline.mouth_mor,
                "yawn_threshold": self._baseline.yawn_threshold,
                "head_pitch_ratio": self._baseline.head_pitch_ratio,
                "head_nod_threshold": self._baseline.head_nod_threshold,
            }
        return res
