"""Posture Analyzer module for VisionGuard.

Performs geometric deviation calculation, continuous posture scoring (0-100),
instantaneous classification, and temporal reasoning (EMA score, sustained-duration filtering).

Formula Documentation:
----------------------
Given normalized deviations from calibrated baseline:
  d_slouch = max(0.0, (baseline.slouch_proxy - current.slouch_proxy) / baseline.slouch_proxy)
  d_fwd = max(0.0, (current.forward_lean_proxy - baseline.forward_lean_proxy) / baseline.forward_lean_proxy)
  d_head_lat = abs(current.head_lateral_displacement - baseline.head_lateral_displacement)
  d_tilt = abs(current.shoulder_tilt - baseline.shoulder_tilt)
  d_torso_lat = abs(current.torso_lateral_displacement - baseline.torso_lateral_displacement)

Weighted total deviation:
  D = 0.35 * d_slouch + 0.25 * d_fwd + 0.20 * d_head_lat + 0.10 * d_tilt + 0.10 * d_torso_lat

Posture Score:
  score = clamp(100.0 * exp(-3.0 * D), 0.0, 100.0)

Properties:
  - 100.0 when D = 0 (identical to baseline)
  - Strictly monotonically decreasing with deviation
  - Strictly bounded in [0.0, 100.0]
  - Independent of categorical posture status and detector confidence.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, Dict, Any

from app.posture.calibration import PostureBaseline
from app.posture.geometry import BodyGeometry


class PostureStatus(str, Enum):
    NOT_CALIBRATED = "NOT_CALIBRATED"
    GOOD = "GOOD"
    SLOUCHING = "SLOUCHING"
    FORWARD_LEAN = "FORWARD_LEAN"
    LEFT_LEAN = "LEFT_LEAN"
    RIGHT_LEAN = "RIGHT_LEAN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PostureResult:
    """Complete output of posture analysis for a frame."""
    instantaneous_status: PostureStatus
    stable_status: PostureStatus
    instantaneous_score: Optional[float]
    smoothed_score: Optional[float]
    confidence: Optional[float]
    total_deviation: float
    deviations: Dict[str, float]


class PostureAnalyzer:
    """Evaluates posture against calibrated baseline with temporal smoothing."""

    # Explicit non-negative weights summing to 1.0
    WEIGHT_SLOUCH: float = 0.35
    WEIGHT_FORWARD: float = 0.25
    WEIGHT_HEAD_LATERAL: float = 0.20
    WEIGHT_TILT: float = 0.10
    WEIGHT_TORSO_LATERAL: float = 0.10

    # Categorical classification thresholds (normalized deviation)
    THRESH_SLOUCH: float = 0.18
    THRESH_FORWARD: float = 0.22
    THRESH_LATERAL: float = 0.12
    THRESH_TILT: float = 0.12

    # Temporal parameters (seconds)
    SUSTAINED_BAD_SECONDS: float = 1.5
    SUSTAINED_GOOD_SECONDS: float = 1.0
    SUSTAINED_UNKNOWN_SECONDS: float = 1.5
    EMA_ALPHA: float = 0.25

    def __init__(self, baseline: Optional[PostureBaseline] = None):
        self._baseline: Optional[PostureBaseline] = baseline
        self._stable_status: PostureStatus = PostureStatus.NOT_CALIBRATED
        self._smoothed_score: Optional[float] = None
        self._candidate_status: Optional[PostureStatus] = None
        self._candidate_start_time: Optional[float] = None
        self._last_timestamp: Optional[float] = None
        self.reset_temporal_state()

    def set_baseline(self, baseline: Optional[PostureBaseline]) -> None:
        """Set or update the baseline, resetting temporal state."""
        self._baseline = baseline
        self.reset_temporal_state()

    def reset_state(self) -> None:
        """Alias for reset_temporal_state."""
        self.reset_temporal_state()

    def reset_temporal_state(self) -> None:
        """Reset temporal smoothing buffers while preserving baseline."""
        self._stable_status = PostureStatus.GOOD if self._baseline is not None else PostureStatus.NOT_CALIBRATED
        self._smoothed_score = 100.0 if self._baseline is not None else None
        self._candidate_status = None
        self._candidate_start_time = None
        self._last_timestamp = None

    def analyze(
        self,
        geometry: Optional[BodyGeometry],
        timestamp: Optional[float] = None,
    ) -> PostureResult:
        """Analyze a frame's geometry against the baseline.

        Uses explicit timestamp if provided for deterministic testing.
        """
        now = time.time() if timestamp is None else timestamp
        self._last_timestamp = now

        if self._baseline is None:
            return PostureResult(
                instantaneous_status=PostureStatus.NOT_CALIBRATED,
                stable_status=PostureStatus.NOT_CALIBRATED,
                instantaneous_score=None,
                smoothed_score=None,
                confidence=None,
                total_deviation=0.0,
                deviations={},
            )

        if geometry is None or geometry.confidence < 0.4:
            # Pose missing or untrustworthy
            instant_status = PostureStatus.UNKNOWN
            instant_score = None
            total_dev = 0.0
            devs: Dict[str, float] = {}
            conf = geometry.confidence if geometry is not None else 0.0
        else:
            # Calculate deviations relative to baseline
            instant_status, instant_score, total_dev, devs = self._evaluate_geometry(geometry)
            conf = geometry.confidence

        # Update EMA score
        if instant_score is not None:
            if self._smoothed_score is None:
                self._smoothed_score = instant_score
            else:
                self._smoothed_score = (
                    self.EMA_ALPHA * instant_score + (1.0 - self.EMA_ALPHA) * self._smoothed_score
                )
            self._smoothed_score = max(0.0, min(100.0, self._smoothed_score))

        # Temporal Reasoning for stable state
        self._update_stable_status(instant_status, now)

        # Build output
        final_score = (
            round(self._smoothed_score, 1)
            if self._smoothed_score is not None and self._stable_status != PostureStatus.UNKNOWN
            else None
        )

        return PostureResult(
            instantaneous_status=instant_status,
            stable_status=self._stable_status,
            instantaneous_score=round(instant_score, 1) if instant_score is not None else None,
            smoothed_score=final_score,
            confidence=round(conf, 4) if conf is not None else None,
            total_deviation=round(total_dev, 4),
            deviations=devs,
        )

    def _evaluate_geometry(
        self, geometry: BodyGeometry
    ) -> Tuple[PostureStatus, float, float, Dict[str, float]]:
        b = self._baseline
        assert b is not None

        # 1. Slouch deviation
        slouch_base = max(b.slouch_proxy, 1e-4)
        d_slouch = max(0.0, (slouch_base - geometry.slouch_proxy) / slouch_base)

        # 2. Forward lean deviation
        fwd_base = max(b.forward_lean_proxy, 1e-4)
        d_fwd = max(0.0, (geometry.forward_lean_proxy - fwd_base) / fwd_base)

        # 3. Head lateral deviation
        head_lat_delta = geometry.head_lateral_displacement - b.head_lateral_displacement
        d_head_lat = abs(head_lat_delta)

        # 4. Shoulder tilt deviation
        tilt_delta = geometry.shoulder_tilt - b.shoulder_tilt
        d_tilt = abs(tilt_delta)

        # 5. Torso lateral deviation
        torso_lat_delta = geometry.torso_lateral_displacement - b.torso_lateral_displacement
        d_torso_lat = abs(torso_lat_delta)

        # Weighted total deviation D
        total_dev = (
            self.WEIGHT_SLOUCH * d_slouch
            + self.WEIGHT_FORWARD * d_fwd
            + self.WEIGHT_HEAD_LATERAL * d_head_lat
            + self.WEIGHT_TILT * d_tilt
            + self.WEIGHT_TORSO_LATERAL * d_torso_lat
        )

        # Continuous Posture Score formula: clamp(100 * exp(-3 * D), 0, 100)
        raw_score = 100.0 * math.exp(-3.0 * total_dev)
        score = max(0.0, min(100.0, raw_score))

        # Categorical Instantaneous State
        if d_fwd >= self.THRESH_FORWARD:
            status = PostureStatus.FORWARD_LEAN
        elif d_slouch >= self.THRESH_SLOUCH:
            status = PostureStatus.SLOUCHING
        elif head_lat_delta > self.THRESH_LATERAL:
            status = PostureStatus.LEFT_LEAN
        elif head_lat_delta < -self.THRESH_LATERAL:
            status = PostureStatus.RIGHT_LEAN
        elif d_tilt >= self.THRESH_TILT:
            status = PostureStatus.LEFT_LEAN if tilt_delta > 0 else PostureStatus.RIGHT_LEAN
        else:
            status = PostureStatus.GOOD

        devs = {
            "d_slouch": round(d_slouch, 4),
            "d_fwd": round(d_fwd, 4),
            "d_head_lat": round(d_head_lat, 4),
            "d_tilt": round(d_tilt, 4),
            "d_torso_lat": round(d_torso_lat, 4),
        }

        return status, score, total_dev, devs

    def _update_stable_status(self, instant_status: PostureStatus, now: float) -> None:
        """Temporal sustained-duration filter for stable posture state."""
        if instant_status == self._stable_status:
            # Instantaneous matches stable: cancel any pending transition
            self._candidate_status = None
            self._candidate_start_time = None
            return

        # Instantaneous differs from stable state
        if self._candidate_status != instant_status:
            # New candidate state starts timing now
            self._candidate_status = instant_status
            self._candidate_start_time = now
            return

        # Same candidate state continues: check duration
        if self._candidate_start_time is None:
            self._candidate_start_time = now
            return

        elapsed = now - self._candidate_start_time

        # Determine required sustained duration
        if instant_status == PostureStatus.GOOD:
            required = self.SUSTAINED_GOOD_SECONDS
        elif instant_status == PostureStatus.UNKNOWN:
            required = self.SUSTAINED_UNKNOWN_SECONDS
        else:
            # Bad posture state (SLOUCHING, FORWARD_LEAN, LEFT_LEAN, RIGHT_LEAN)
            required = self.SUSTAINED_BAD_SECONDS

        if elapsed >= required:
            # Sustained long enough: transition stable state
            self._stable_status = instant_status
            self._candidate_status = None
            self._candidate_start_time = None
