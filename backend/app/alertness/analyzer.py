"""Alertness Analyzer & Temporal Evidence Fusion.

Combines personalized eye closure duration, blink events & rate, PERCLOS proxy,
sustained yawns, and head drops into a continuous 0-100 alertness score.
Applies temporal hysteresis to produce typed alertness states:
ALERT, POSSIBLE_DROWSINESS, UNKNOWN, NOT_CALIBRATED.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, Deque, Tuple

from app.alertness.config import AlertnessConfig, DEFAULT_CONFIG
from app.alertness.geometry import FaceGeometry
from app.alertness.calibration import AlertnessBaseline


class AlertnessStatus(str, Enum):
    NOT_CALIBRATED = "NOT_CALIBRATED"
    ALERT = "ALERT"
    POSSIBLE_DROWSINESS = "POSSIBLE_DROWSINESS"
    UNKNOWN = "UNKNOWN"


@dataclass
class AlertnessAnalysisResult:
    status: AlertnessStatus
    score: Optional[float]
    eye_state: str  # "OPEN", "CLOSED", "UNKNOWN"
    eye_closure_duration: Optional[float]
    blink_rate: Optional[float]
    yawn_score: Optional[float]
    head_pitch: Optional[float]
    head_nod_signal: bool
    perclos_proxy: Optional[float]
    evidence_score: float
    confidence: float
    debug_metrics: Dict[str, Any] = field(default_factory=dict)
    blink_count: int = 0
    longest_eye_closure: float = 0.0
    valid_eye_tracking_seconds: float = 0.0
    ear: Optional[float] = None
    closed_eye_threshold: Optional[float] = None
    is_blink_candidate: bool = False


class AlertnessAnalyzer:
    """Performs multi-signal temporal fusion and hysteresis on facial geometry."""

    def __init__(self, config: AlertnessConfig = DEFAULT_CONFIG):
        self._config = config
        self._baseline: Optional[AlertnessBaseline] = None

        # State tracking
        self._current_status: AlertnessStatus = AlertnessStatus.ALERT
        self._last_timestamp: Optional[float] = None
        self._valid_observation_sec: float = 0.0

        # Eye closure
        self._eye_closure_started_at: Optional[float] = None
        self._current_closure_duration: float = 0.0
        self._is_blink_candidate: bool = False

        # Blinks
        self._blink_timestamps: Deque[float] = deque()
        self._total_blink_count: int = 0
        self._longest_eye_closure: float = 0.0
        self.candidate_history: Deque[Dict[str, Any]] = deque(maxlen=100)

        # PERCLOS rolling intervals: deque of (timestamp, duration_sec, is_closed)
        self._perclos_intervals: Deque[Tuple[float, float, bool]] = deque()

        # Yawn tracking
        self._mouth_open_started_at: Optional[float] = None
        self._yawn_active: bool = False
        self._yawn_timestamps: Deque[float] = deque()

        # Head drop / nod tracking
        self._head_drop_started_at: Optional[float] = None
        self._head_nod_active: bool = False

        # Hysteresis timers
        self._evidence_entry_started_at: Optional[float] = None
        self._continuous_open_started_at: Optional[float] = None

    @property
    def is_calibrated(self) -> bool:
        return self._baseline is not None

    def _record_candidate(self, duration: float, accepted: bool, reason: str) -> None:
        if not hasattr(self, "candidate_history"):
            self.candidate_history = deque(maxlen=100)
        self.candidate_history.append({
            "timestamp": time.time(),
            "duration": round(duration, 4),
            "accepted": accepted,
            "reason": reason,
        })

    def set_baseline(self, baseline: Optional[AlertnessBaseline]) -> None:
        """Set or update the active personalized baseline."""
        self._baseline = baseline
        self.reset_state()

    def reset_state(self) -> None:
        """Reset temporal state buffers."""
        self._current_status = AlertnessStatus.ALERT
        self._last_timestamp = None
        self._valid_observation_sec = 0.0
        self._eye_closure_started_at = None
        self._current_closure_duration = 0.0
        self._blink_timestamps.clear()
        self._total_blink_count = 0
        self._longest_eye_closure = 0.0
        self._is_blink_candidate = False
        self._perclos_intervals.clear()
        self._mouth_open_started_at = None
        self._yawn_active = False
        self._yawn_timestamps.clear()
        self._head_drop_started_at = None
        self._head_nod_active = False
        self._evidence_entry_started_at = None
        self._continuous_open_started_at = None

    def analyze(
        self,
        geometry: Optional[FaceGeometry],
        timestamp: Optional[float] = None,
    ) -> AlertnessAnalysisResult:
        """Analyze a frame's FaceGeometry and produce an AlertnessAnalysisResult."""
        now = time.time() if timestamp is None else timestamp

        # Uncalibrated guard
        if self._baseline is None:
            return AlertnessAnalysisResult(
                status=AlertnessStatus.NOT_CALIBRATED,
                score=None,
                eye_state="UNKNOWN",
                eye_closure_duration=None,
                blink_rate=None,
                yawn_score=None,
                head_pitch=geometry.head_pitch_ratio if geometry else None,
                head_nod_signal=False,
                perclos_proxy=None,
                evidence_score=0.0,
                confidence=0.0,
                debug_metrics={"reason": "not_calibrated"},
                blink_count=self._total_blink_count,
                longest_eye_closure=self._longest_eye_closure,
                valid_eye_tracking_seconds=round(self._valid_observation_sec, 1),
                ear=None,
                closed_eye_threshold=self._baseline.closed_eye_threshold if self._baseline else None,
                is_blink_candidate=False,
            )

        # Missing or invalid face guard
        if geometry is None or not geometry.is_valid or geometry.combined_ear is None:
            if self._is_blink_candidate and self._eye_closure_started_at is not None:
                duration = now - self._eye_closure_started_at
                self._record_candidate(duration, accepted=False, reason="cancelled_by_tracking_loss")
            # Freeze timers and return UNKNOWN (tracking loss cancels pending candidate)
            self._eye_closure_started_at = None
            self._is_blink_candidate = False
            self._mouth_open_started_at = None
            self._head_drop_started_at = None
            self._evidence_entry_started_at = None
            self._continuous_open_started_at = None
            self._last_timestamp = None

            return AlertnessAnalysisResult(
                status=AlertnessStatus.UNKNOWN,
                score=None,
                eye_state="UNKNOWN",
                eye_closure_duration=None,
                blink_rate=None,
                yawn_score=None,
                head_pitch=None,
                head_nod_signal=False,
                perclos_proxy=None,
                evidence_score=0.0,
                confidence=0.0,
                debug_metrics={"reason": "face_missing_or_invalid"},
                blink_count=self._total_blink_count,
                longest_eye_closure=self._longest_eye_closure,
                valid_eye_tracking_seconds=round(self._valid_observation_sec, 1),
                ear=None,
                closed_eye_threshold=self._baseline.closed_eye_threshold if self._baseline else None,
                is_blink_candidate=False,
            )

        # Delta time calculation
        if self._last_timestamp is None:
            dt = 0.033  # Initial nominal step (~30 FPS)
        else:
            dt = max(0.001, min(1.0, now - self._last_timestamp))
        self._last_timestamp = now
        self._valid_observation_sec += dt

        # --- 1. Eye State & Closure Timing ---
        combined_ear = geometry.combined_ear
        closed_thresh = self._baseline.closed_eye_threshold
        is_closed = combined_ear < closed_thresh

        if is_closed:
            eye_state = "CLOSED"
            if self._eye_closure_started_at is None:
                self._eye_closure_started_at = now
                self._is_blink_candidate = True

            self._current_closure_duration = now - self._eye_closure_started_at
            if self._current_closure_duration > self._config.blink_max_duration_sec:
                # Sustained closure is not a normal transient blink
                if self._is_blink_candidate:
                    self._record_candidate(self._current_closure_duration, accepted=False, reason="sustained_closure_exceeded_max")
                self._is_blink_candidate = False

            if self._current_closure_duration > self._longest_eye_closure:
                self._longest_eye_closure = round(self._current_closure_duration, 2)
            self._continuous_open_started_at = None
        else:
            eye_state = "OPEN"
            if self._eye_closure_started_at is not None:
                closed_dur = now - self._eye_closure_started_at
                self._eye_closure_started_at = None
                if closed_dur > self._longest_eye_closure:
                    self._longest_eye_closure = round(closed_dur, 2)
                # Increment blink exactly once if candidate and within valid blink bounds
                if self._is_blink_candidate:
                    if closed_dur < self._config.blink_min_duration_sec:
                        self._record_candidate(closed_dur, accepted=False, reason="too_short")
                    elif closed_dur > self._config.blink_max_duration_sec:
                        self._record_candidate(closed_dur, accepted=False, reason="too_long")
                    else:
                        self._blink_timestamps.append(now)
                        self._total_blink_count += 1
                        self._record_candidate(closed_dur, accepted=True, reason="valid_blink")
                else:
                    self._record_candidate(closed_dur, accepted=False, reason="candidate_previously_invalidated")
                self._is_blink_candidate = False

            self._current_closure_duration = 0.0
            if self._continuous_open_started_at is None:
                self._continuous_open_started_at = now

        # --- 2. Blink Rate ---
        # Prune blinks older than 60s
        while self._blink_timestamps and (now - self._blink_timestamps[0] > 60.0):
            self._blink_timestamps.popleft()

        if self._valid_observation_sec < self._config.blink_rate_min_observation_sec:
            blink_rate = None
        else:
            obs_win = min(60.0, self._valid_observation_sec)
            blink_rate = round(len(self._blink_timestamps) * (60.0 / obs_win), 1)

        # --- 3. PERCLOS-like Temporal Proxy ---
        self._perclos_intervals.append((now, dt, is_closed))
        # Prune intervals older than rolling window
        while self._perclos_intervals and (now - self._perclos_intervals[0][0] > self._config.perclos_window_sec):
            self._perclos_intervals.popleft()

        total_obs_time = sum(item[1] for item in self._perclos_intervals)
        closed_obs_time = sum(item[1] for item in self._perclos_intervals if item[2])

        if total_obs_time >= 3.0:
            perclos_proxy = round(closed_obs_time / total_obs_time, 3)
        else:
            perclos_proxy = 0.0

        # --- 4. Yawn Signal ---
        mor = geometry.mouth_ratio
        if mor is not None and mor >= self._baseline.yawn_threshold:
            if self._mouth_open_started_at is None:
                self._mouth_open_started_at = now
            yawn_dur = now - self._mouth_open_started_at
            if yawn_dur >= self._config.yawn_min_duration_sec:
                if not self._yawn_active:
                    self._yawn_active = True
                    self._yawn_timestamps.append(now)
        else:
            self._mouth_open_started_at = None
            self._yawn_active = False

        # Prune old yawns
        while self._yawn_timestamps and (now - self._yawn_timestamps[0] > self._config.yawn_window_sec):
            self._yawn_timestamps.popleft()

        yawn_score = round(min(1.0, len(self._yawn_timestamps) * 0.35 + (0.5 if self._yawn_active else 0.0)), 2)

        # --- 5. Head Nod / Drop Signal ---
        pitch = geometry.head_pitch_ratio
        if pitch is not None and pitch >= self._baseline.head_nod_threshold:
            if self._head_drop_started_at is None:
                self._head_drop_started_at = now
            drop_dur = now - self._head_drop_started_at
            head_nod_signal = drop_dur >= self._config.head_nod_min_duration_sec
        else:
            self._head_drop_started_at = None
            head_nod_signal = False
        self._head_nod_active = head_nod_signal

        # --- 6. Evidence Scoring & Continuous Alertness ---
        # A. Sustained closure evidence
        if self._current_closure_duration >= self._config.sustained_closure_critical_sec:
            ev_closure = 1.0
        elif self._current_closure_duration >= self._config.sustained_closure_warn_sec:
            frac = (self._current_closure_duration - self._config.sustained_closure_warn_sec) / (
                self._config.sustained_closure_critical_sec - self._config.sustained_closure_warn_sec
            )
            ev_closure = 0.40 + 0.60 * frac
        else:
            ev_closure = 0.0

        # B. PERCLOS evidence
        ev_perclos = min(1.0, perclos_proxy / max(0.01, self._config.perclos_drowsy_threshold))

        # C. Yawn evidence
        ev_yawn = min(1.0, yawn_score)

        # D. Head nod evidence
        ev_nod = 0.70 if head_nod_signal else 0.0

        # Weighted combination
        fused_evidence = (
            self._config.weight_sustained_closure * ev_closure
            + self._config.weight_perclos * ev_perclos
            + self._config.weight_yawn * ev_yawn
            + self._config.weight_head_nod * ev_nod
        )

        # Critical single-channel override: sustained eye closure can independently drive high evidence
        if ev_closure >= self._config.evidence_entry_threshold:
            fused_evidence = max(fused_evidence, ev_closure)

        fused_evidence = round(max(0.0, min(1.0, fused_evidence)), 3)
        continuous_score = round(max(0.0, min(100.0, 100.0 * (1.0 - fused_evidence))), 1)

        # --- 7. Temporal Hysteresis State Machine ---
        if self._current_status == AlertnessStatus.ALERT:
            if fused_evidence >= self._config.evidence_entry_threshold:
                self._current_status = AlertnessStatus.POSSIBLE_DROWSINESS
                self._continuous_open_started_at = None
            self._evidence_entry_started_at = None

        elif self._current_status == AlertnessStatus.POSSIBLE_DROWSINESS:
            if fused_evidence <= self._config.evidence_recovery_threshold and eye_state == "OPEN":
                if self._continuous_open_started_at is not None:
                    if now - self._continuous_open_started_at >= self._config.recovery_open_time_sec:
                        self._current_status = AlertnessStatus.ALERT
                        self._evidence_entry_started_at = None
            else:
                self._continuous_open_started_at = None

        confidence = geometry.confidence

        debug_metrics = {
            "left_ear": round(geometry.left_ear, 4) if geometry.left_ear is not None else None,
            "right_ear": round(geometry.right_ear, 4) if geometry.right_ear is not None else None,
            "combined_ear": round(combined_ear, 4),
            "open_eye_baseline": self._baseline.open_eye_ear,
            "closed_threshold": self._baseline.closed_eye_threshold,
            "mouth_ratio": round(mor, 4) if mor is not None else None,
            "mouth_baseline": self._baseline.mouth_mor,
            "yawn_threshold": self._baseline.yawn_threshold,
            "head_pitch": round(pitch, 4) if pitch is not None else None,
            "head_pitch_baseline": self._baseline.head_pitch_ratio,
            "head_nod_threshold": self._baseline.head_nod_threshold,
            "ev_closure": round(ev_closure, 3),
            "ev_perclos": round(ev_perclos, 3),
            "ev_yawn": round(ev_yawn, 3),
            "ev_nod": round(ev_nod, 3),
            "evidence_score": fused_evidence,
            "valid_observation_sec": round(self._valid_observation_sec, 1),
        }

        return AlertnessAnalysisResult(
            status=self._current_status,
            score=continuous_score,
            eye_state=eye_state,
            eye_closure_duration=round(self._current_closure_duration, 2),
            blink_rate=blink_rate,
            yawn_score=yawn_score,
            head_pitch=round(pitch, 3) if pitch is not None else None,
            head_nod_signal=head_nod_signal,
            perclos_proxy=perclos_proxy,
            evidence_score=fused_evidence,
            confidence=round(confidence, 2),
            debug_metrics=debug_metrics,
            blink_count=self._total_blink_count,
            longest_eye_closure=self._longest_eye_closure,
            valid_eye_tracking_seconds=round(self._valid_observation_sec, 1),
            ear=combined_ear,
            closed_eye_threshold=closed_thresh,
            is_blink_candidate=self._is_blink_candidate,
        )
