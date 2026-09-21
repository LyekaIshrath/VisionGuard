"""VisionGuard Mission 05: Temporal Risk Engine.

Consumes derived HumanState telemetry and evaluates independent domain risks
(Posture and Alertness) using monotonic time, duration-based accumulation,
severity weighting, observation pausing, and asymmetric hysteresis.
"""

from __future__ import annotations

import time
import threading
from typing import Optional, List, Tuple

from app.human_state.models import HumanState
from app.intelligence.risk_config import RiskConfig, DEFAULT_RISK_CONFIG
from app.intelligence.risk_models import (
    RiskLevel,
    RiskCategory,
    RiskReasonCode,
    DomainRiskState,
    OverallRiskState,
)


class RiskEngine:
    """Thread-safe temporal risk engine evaluating derived HumanState."""

    def __init__(self, config: RiskConfig = DEFAULT_RISK_CONFIG) -> None:
        self._config = config
        self._lock = threading.Lock()

        # Session tracking
        self._is_active: bool = False

        # --- Posture Domain Accumulator ---
        # Continuous non-GOOD posture timer
        self._posture_non_good_duration: float = 0.0
        self._posture_good_recovery_duration: float = 0.0
        self._last_posture_timestamp: Optional[float] = None
        self._last_valid_posture_timestamp: Optional[float] = None
        self._current_posture_risk_score: float = 0.0

        # --- Alertness Domain Accumulator ---
        # Continuous POSSIBLE_DROWSINESS timer
        self._alertness_drowsy_duration: float = 0.0
        self._alertness_recovery_duration: float = 0.0
        self._last_alertness_timestamp: Optional[float] = None
        self._last_valid_alertness_timestamp: Optional[float] = None
        self._current_alertness_risk_score: float = 0.0

        # --- Overall Temporal Hysteresis State Machine ---
        self._overall_level: RiskLevel = RiskLevel.UNKNOWN
        self._pending_level: Optional[RiskLevel] = None
        self._pending_level_since: Optional[float] = None

        # Most recent evaluation snapshot
        self._latest_risk_state: OverallRiskState = self._create_initial_state()

    def reset(self) -> None:
        """Reset temporal duration accumulators and state machine for new session."""
        self._is_active = False
        self._posture_non_good_duration = 0.0
        self._posture_good_recovery_duration = 0.0
        self._last_posture_timestamp = None
        self._last_valid_posture_timestamp = None
        self._current_posture_risk_score = 0.0

        self._alertness_drowsy_duration = 0.0
        self._alertness_recovery_duration = 0.0
        self._last_alertness_timestamp = None
        self._last_valid_alertness_timestamp = None
        self._current_alertness_risk_score = 0.0

        self._overall_level = RiskLevel.UNKNOWN
        self._pending_level = None
        self._pending_level_since = None
        self._latest_risk_state = self._create_initial_state()

    def _create_initial_state(self) -> OverallRiskState:
        p_state = DomainRiskState(
            category=RiskCategory.POSTURE,
            level=RiskLevel.UNKNOWN,
            score=None,
            is_valid=False,
            active_duration_sec=0.0,
            reasons=[RiskReasonCode.INSUFFICIENT_OBSERVATION],
        )
        a_state = DomainRiskState(
            category=RiskCategory.ALERTNESS,
            level=RiskLevel.UNKNOWN,
            score=None,
            is_valid=False,
            active_duration_sec=0.0,
            reasons=[RiskReasonCode.INSUFFICIENT_OBSERVATION],
        )
        return OverallRiskState(
            level=RiskLevel.UNKNOWN,
            score=None,
            posture_risk=p_state,
            alertness_risk=a_state,
            dominant_category=None,
            active_reasons=[RiskReasonCode.INSUFFICIENT_OBSERVATION],
            confidence=0.0,
        )

    def reset_session(self) -> None:
        """Reset transient accumulators on new monitoring session (POST /monitoring/start)."""
        with self._lock:
            self._is_active = True
            self._posture_non_good_duration = 0.0
            self._posture_good_recovery_duration = 0.0
            self._last_posture_timestamp = None
            self._last_valid_posture_timestamp = None
            self._current_posture_risk_score = 0.0

            self._alertness_drowsy_duration = 0.0
            self._alertness_recovery_duration = 0.0
            self._last_alertness_timestamp = None
            self._last_valid_alertness_timestamp = None
            self._current_alertness_risk_score = 0.0

            self._overall_level = RiskLevel.UNKNOWN
            self._pending_level = None
            self._pending_level_since = None
            self._latest_risk_state = self._create_initial_state()

    def stop_session(self) -> None:
        """Stop accumulation on monitoring stop (POST /monitoring/stop)."""
        with self._lock:
            self._is_active = False
            self._last_posture_timestamp = None
            self._last_alertness_timestamp = None

    def evaluate(
        self,
        human_state: Optional[HumanState],
        timestamp: Optional[float] = None,
    ) -> OverallRiskState:
        """Evaluate derived HumanState at monotonic timestamp.

        Args:
            human_state: The current HumanState computed by PerceptionEngine.
            timestamp: Monotonic seconds. If None, uses time.monotonic().
        """
        now = timestamp if timestamp is not None else time.monotonic()

        with self._lock:
            # 1. Posture Domain Evaluation
            p_state = self._evaluate_posture_domain(human_state, now)

            # 2. Alertness Domain Evaluation
            a_state = self._evaluate_alertness_domain(human_state, now)

            # 3. Domain Fusion & Overall Score Calculation
            fused_score, overall_level, dominant_cat = self._fuse_domains(p_state, a_state, now)

            # Active reasons aggregation
            active_reasons: List[RiskReasonCode] = []
            if p_state.is_valid and p_state.level in (RiskLevel.MODERATE, RiskLevel.HIGH):
                active_reasons.extend(p_state.reasons)
            if a_state.is_valid and a_state.level in (RiskLevel.MODERATE, RiskLevel.HIGH):
                active_reasons.extend(a_state.reasons)

            if not p_state.is_valid and not a_state.is_valid:
                active_reasons = [RiskReasonCode.INSUFFICIENT_OBSERVATION]

            # Overall confidence
            conf = human_state.confidence if (human_state and human_state.confidence is not None) else 0.0

            result = OverallRiskState(
                level=overall_level,
                score=fused_score,
                posture_risk=p_state,
                alertness_risk=a_state,
                dominant_category=dominant_cat,
                active_reasons=active_reasons,
                confidence=conf,
            )
            self._latest_risk_state = result
            return result

    def _evaluate_posture_domain(
        self,
        state: Optional[HumanState],
        now: float,
    ) -> DomainRiskState:
        """Evaluate posture risk using duration + severity, with observation pause & stale timeout."""
        dt = (now - self._last_posture_timestamp) if self._last_posture_timestamp is not None else 0.1
        dt = max(0.001, min(1.0, dt))
        self._last_posture_timestamp = now

        # Check observation validity
        pose_valid = (
            state is not None
            and state.pose_detected
            and state.posture_status is not None
            and state.posture_status not in ("NOT_CALIBRATED", "UNKNOWN")
        )

        if not pose_valid:
            # Observation is UNKNOWN / paused.
            # Stale evidence check: if valid observation has been gone > stale_observation_timeout_sec,
            # invalidate previous active evidence without manufacturing a LOW recovery event.
            if self._last_valid_posture_timestamp is not None:
                if (now - self._last_valid_posture_timestamp) > self._config.stale_observation_timeout_sec:
                    self._posture_non_good_duration = 0.0
                    self._current_posture_risk_score = 0.0

            return DomainRiskState(
                category=RiskCategory.POSTURE,
                level=RiskLevel.UNKNOWN,
                score=None,
                is_valid=False,
                active_duration_sec=self._posture_non_good_duration,
                reasons=[RiskReasonCode.INSUFFICIENT_OBSERVATION],
            )

        # Pose is valid
        self._last_valid_posture_timestamp = now
        p_status = state.posture_status
        p_score = state.posture_score if state.posture_score is not None else 100.0

        reasons: List[RiskReasonCode] = []
        if p_status == "GOOD":
            # Decays bad posture duration
            decay_amount = dt * (self._config.posture_high_duration_sec / self._config.posture_recovery_time_sec)
            self._posture_non_good_duration = max(0.0, self._posture_non_good_duration - decay_amount)
            self._posture_good_recovery_duration += dt
        else:
            # Bad posture (SLOUCHING, FORWARD_LEAN, LEFT_LEAN, RIGHT_LEAN)
            self._posture_non_good_duration += dt
            self._posture_good_recovery_duration = 0.0

            if p_status == "SLOUCHING":
                reasons.append(RiskReasonCode.SUSTAINED_SLOUCH)
            elif p_status == "FORWARD_LEAN":
                reasons.append(RiskReasonCode.SUSTAINED_FORWARD_LEAN)
            elif p_status == "LEFT_LEAN":
                reasons.append(RiskReasonCode.SUSTAINED_LEFT_LEAN)
            elif p_status == "RIGHT_LEAN":
                reasons.append(RiskReasonCode.SUSTAINED_RIGHT_LEAN)
            else:
                reasons.append(RiskReasonCode.POSTURE_DEVIATION)

        # Combine duration fraction (0-1) and severity fraction (0-1 from posture_score where 100 is best, 0 is worst)
        duration_frac = min(1.0, self._posture_non_good_duration / max(1.0, self._config.posture_high_duration_sec))
        severity_frac = max(0.0, min(1.0, (100.0 - p_score) / 100.0))

        if self._posture_non_good_duration <= 0.0:
            raw_score = 0.0
        else:
            combined_frac = (
                self._config.posture_duration_weight * duration_frac
                + self._config.posture_severity_weight * severity_frac
            )
            # Scale to 0-100
            raw_score = 100.0 * combined_frac

        self._current_posture_risk_score = round(max(0.0, min(100.0, raw_score)), 1)

        # Assign domain risk level with duration thresholds
        if self._posture_non_good_duration >= self._config.posture_high_duration_sec:
            p_level = RiskLevel.HIGH
        elif self._posture_non_good_duration >= self._config.posture_warn_duration_sec:
            p_level = RiskLevel.MODERATE
        else:
            p_level = RiskLevel.LOW

        return DomainRiskState(
            category=RiskCategory.POSTURE,
            level=p_level,
            score=self._current_posture_risk_score,
            is_valid=True,
            active_duration_sec=round(self._posture_non_good_duration, 2),
            reasons=reasons if p_level in (RiskLevel.MODERATE, RiskLevel.HIGH) else [],
        )

    def _evaluate_alertness_domain(
        self,
        state: Optional[HumanState],
        now: float,
    ) -> DomainRiskState:
        """Evaluate alertness risk from Mission 04 derived telemetry."""
        dt = (now - self._last_alertness_timestamp) if self._last_alertness_timestamp is not None else 0.1
        dt = max(0.001, min(1.0, dt))
        self._last_alertness_timestamp = now

        # Check observation validity
        face_valid = (
            state is not None
            and state.face_detected
            and state.alertness_status is not None
            and state.alertness_status not in ("NOT_CALIBRATED", "UNKNOWN")
        )

        if not face_valid:
            # Observation is UNKNOWN / paused.
            # Stale timeout check
            if self._last_valid_alertness_timestamp is not None:
                if (now - self._last_valid_alertness_timestamp) > self._config.stale_observation_timeout_sec:
                    self._alertness_drowsy_duration = 0.0
                    self._current_alertness_risk_score = 0.0

            return DomainRiskState(
                category=RiskCategory.ALERTNESS,
                level=RiskLevel.UNKNOWN,
                score=None,
                is_valid=False,
                active_duration_sec=self._alertness_drowsy_duration,
                reasons=[RiskReasonCode.INSUFFICIENT_OBSERVATION],
            )

        # Face is valid
        self._last_valid_alertness_timestamp = now
        a_status = state.alertness_status
        a_score = state.alertness_score if state.alertness_score is not None else 100.0
        closure_dur = state.eye_closure_duration if state.eye_closure_duration is not None else 0.0

        reasons: List[RiskReasonCode] = []
        if a_status == "ALERT":
            # Normal alert status decay
            decay_amount = dt * (self._config.alertness_high_duration_sec / self._config.alertness_recovery_time_sec)
            self._alertness_drowsy_duration = max(0.0, self._alertness_drowsy_duration - decay_amount)
            self._alertness_recovery_duration += dt
        elif a_status == "POSSIBLE_DROWSINESS":
            self._alertness_drowsy_duration += dt
            self._alertness_recovery_duration = 0.0
            reasons.append(RiskReasonCode.POSSIBLE_DROWSINESS)

        # Critical prolonged eye closure check
        if closure_dur >= self._config.critical_eye_closure_sec:
            reasons.append(RiskReasonCode.PROLONGED_EYE_CLOSURE)

        # Severity fraction (0-1 from 100-alertness_score)
        severity_frac = max(0.0, min(1.0, (100.0 - a_score) / 100.0))
        duration_frac = min(1.0, self._alertness_drowsy_duration / max(0.1, self._config.alertness_high_duration_sec))

        if closure_dur >= self._config.critical_eye_closure_sec:
            # Independent single-channel override for critical closure
            raw_score = max(80.0, 100.0 * min(1.0, closure_dur / 3.0))
        elif self._alertness_drowsy_duration <= 0.0 and closure_dur < 0.5:
            raw_score = 0.0
        else:
            raw_score = 100.0 * (0.60 * duration_frac + 0.40 * severity_frac)

        self._current_alertness_risk_score = round(max(0.0, min(100.0, raw_score)), 1)

        # Determine domain risk level
        if (
            self._alertness_drowsy_duration >= self._config.alertness_high_duration_sec
            or closure_dur >= self._config.critical_eye_closure_sec
        ):
            a_level = RiskLevel.HIGH
        elif (
            self._alertness_drowsy_duration >= self._config.alertness_warn_duration_sec
            or self._current_alertness_risk_score >= self._config.hysteresis_moderate_entry
        ):
            a_level = RiskLevel.MODERATE
        else:
            a_level = RiskLevel.LOW

        return DomainRiskState(
            category=RiskCategory.ALERTNESS,
            level=a_level,
            score=self._current_alertness_risk_score,
            is_valid=True,
            active_duration_sec=round(self._alertness_drowsy_duration, 2),
            reasons=reasons if a_level in (RiskLevel.MODERATE, RiskLevel.HIGH) else [],
        )

    def _fuse_domains(
        self,
        p_state: DomainRiskState,
        a_state: DomainRiskState,
        now: float,
    ) -> Tuple[Optional[float], RiskLevel, Optional[RiskCategory]]:
        """Nonlinear dominant-risk fusion with temporal hysteresis."""
        # 1. Both UNKNOWN -> overall UNKNOWN
        if not p_state.is_valid and not a_state.is_valid:
            self._overall_level = RiskLevel.UNKNOWN
            self._pending_level = None
            self._pending_level_since = None
            return None, RiskLevel.UNKNOWN, None

        # 2. Only one domain valid -> preserve valid domain cautiously
        if p_state.is_valid and not a_state.is_valid:
            fused_score = p_state.score or 0.0
            dominant_cat = RiskCategory.POSTURE
        elif a_state.is_valid and not p_state.is_valid:
            fused_score = a_state.score or 0.0
            dominant_cat = RiskCategory.ALERTNESS
        else:
            # 3. Both domains valid: bounded dominant-risk fusion
            p_sc = p_state.score or 0.0
            a_sc = a_state.score or 0.0
            max_sc = max(p_sc, a_sc)
            min_sc = min(p_sc, a_sc)
            dominant_cat = RiskCategory.POSTURE if p_sc >= a_sc else RiskCategory.ALERTNESS

            # Cross-coupling: subtle addition only if both are non-zero, bounded strictly to 100.0
            fused_raw = max_sc + (self._config.cross_coupling_weight * min_sc)
            fused_score = round(max(0.0, min(100.0, fused_raw)), 1)

        # 4. Temporal Hysteresis State Machine for Overall Level
        # Target level based on raw thresholds
        if fused_score >= self._config.hysteresis_high_entry:
            target_level = RiskLevel.HIGH
        elif fused_score >= self._config.hysteresis_moderate_entry:
            target_level = RiskLevel.MODERATE
        else:
            target_level = RiskLevel.LOW

        # Asymmetric hysteresis transition rules:
        # If currently UNKNOWN: adopt target directly
        if self._overall_level == RiskLevel.UNKNOWN:
            self._overall_level = target_level
            self._pending_level = None
            self._pending_level_since = None
            return fused_score, self._overall_level, dominant_cat

        # Current vs Target
        if target_level == self._overall_level:
            self._pending_level = None
            self._pending_level_since = None
        else:
            # Determining if target represents escalation or recovery
            is_escalation = (
                (self._overall_level == RiskLevel.LOW and target_level in (RiskLevel.MODERATE, RiskLevel.HIGH))
                or (self._overall_level == RiskLevel.MODERATE and target_level == RiskLevel.HIGH)
            )

            # Recovery thresholds (must drop below exit threshold to de-escalate)
            is_valid_recovery = False
            if self._overall_level == RiskLevel.HIGH and fused_score <= self._config.hysteresis_high_exit:
                is_valid_recovery = True
            elif self._overall_level == RiskLevel.MODERATE and fused_score <= self._config.hysteresis_moderate_exit:
                is_valid_recovery = True

            required_sustain = (
                self._config.level_entry_sustain_sec if is_escalation else self._config.level_recovery_sustain_sec
            )

            # Critical eye closure immediate escalation bypass
            if a_state.is_valid and RiskReasonCode.PROLONGED_EYE_CLOSURE in a_state.reasons:
                self._overall_level = RiskLevel.HIGH
                self._pending_level = None
                self._pending_level_since = None
                return fused_score, self._overall_level, dominant_cat

            if is_escalation or is_valid_recovery:
                if self._pending_level != target_level:
                    self._pending_level = target_level
                    self._pending_level_since = now
                elif self._pending_level_since is not None and (now - self._pending_level_since) >= required_sustain:
                    self._overall_level = target_level
                    self._pending_level = None
                    self._pending_level_since = None

        return fused_score, self._overall_level, dominant_cat

    @property
    def latest_state(self) -> OverallRiskState:
        with self._lock:
            return self._latest_risk_state
