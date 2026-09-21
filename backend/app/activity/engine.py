"""VisionGuard Work Activity Engine.

Classifies observable workstation interaction states:
- ENGAGED: Person present with recent workstation input/interaction
- OBSERVING: Person present, facing workstation, reading / thinking / reviewing (low/no input)
- ATTENTION_AWAY: Person present, sustained head orientation away from workstation
- AWAY: Person absent for sustained period
- UNKNOWN: Insufficient or uncalibrated optical/workstation signals

CRITICAL DESIGN PRINCIPLES:
- Reports strictly OBSERVABLE physical interaction without productivity judgments.
- NEVER uses judgmental or evaluative labels (e.g. PRODUCTIVE, UNPRODUCTIVE, LAZY, WORKING, NOT_WORKING).
- ENGAGED requires person present AND recent genuine workstation input/activity.
- Screen activity is SUPPORTING CONTEXT only; screen changes alone NEVER independently trigger ENGAGED.
- Blink count MUST NOT independently cause ENGAGED (blinking is an involuntary physiological reflex).
- OBSERVING represents legitimate cognitive work (reading, reviewing code, thinking, watching).
- Applies temporal hysteresis (2.0s dwell) to prevent rapid frame-by-frame state flickering.
"""

from __future__ import annotations

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from app.human_state.models import HumanState
from app.activity.collector import ActivitySnapshot


# Centralized Configuration Thresholds
RECENT_INPUT_ACTIVE_SECONDS: float = 15.0      # Input within 15s indicates current interaction
LOW_ACTIVITY_ENTRY_SECONDS: float = 30.0       # Idle > 30s enters OBSERVING (reading/thinking/reviewing)
ATTENTION_AWAY_ENTRY_SECONDS: float = 8.0      # Head yaw away >= 8s enters ATTENTION_AWAY
AWAY_ENTRY_SECONDS: float = 5.0                # Person absent >= 5s enters AWAY
STATE_DWELL_SECONDS: float = 2.0               # Minimum dwell time before switching states (hysteresis)
HEAD_AWAY_YAW_DEGREES: float = 25.0            # Head yaw threshold in degrees

# Backward-compatibility aliases
IDLE_ACTIVE_THRESHOLD_SEC = RECENT_INPUT_ACTIVE_SECONDS
HEAD_AWAY_YAW_DEGREE_THRESHOLD = HEAD_AWAY_YAW_DEGREES
HEAD_AWAY_SUSTAINED_SEC = ATTENTION_AWAY_ENTRY_SECONDS
PERSON_AWAY_SUSTAINED_SEC = AWAY_ENTRY_SECONDS
HYSTERESIS_CONFIRMATION_SEC = STATE_DWELL_SECONDS


@dataclass(frozen=True)
class WorkActivityConfig:
    """Centralized thresholds for workstation activity state classification."""
    recent_input_active_seconds: float = RECENT_INPUT_ACTIVE_SECONDS
    low_activity_entry_seconds: float = LOW_ACTIVITY_ENTRY_SECONDS
    attention_away_entry_seconds: float = ATTENTION_AWAY_ENTRY_SECONDS
    away_entry_seconds: float = AWAY_ENTRY_SECONDS
    state_dwell_seconds: float = STATE_DWELL_SECONDS
    head_away_yaw_degrees: float = HEAD_AWAY_YAW_DEGREES


DEFAULT_ACTIVITY_CONFIG = WorkActivityConfig()


class WorkActivityState(str, Enum):
    ENGAGED = "ENGAGED"
    OBSERVING = "OBSERVING"
    ATTENTION_AWAY = "ATTENTION_AWAY"
    AWAY = "AWAY"
    UNKNOWN = "UNKNOWN"

    # Backward-compatible aliases
    ACTIVE = "ENGAGED"
    LOW_ACTIVITY = "OBSERVING"


@dataclass
class WorkActivityDecision:
    state: WorkActivityState
    score: float                       # Observable intensity (0-100), NOT a productivity grade
    confidence: float                  # Signal quality (0.0 - 1.0)
    reason_codes: List[str]            # Objective physical reasons
    dwell_duration: float              # Elapsed seconds in current state
    snapshot: Optional[ActivitySnapshot] = None


class WorkActivityEngine:
    """Observes multivariant workstation signals and classifies activity state."""

    def __init__(
        self,
        config: Optional[WorkActivityConfig] = None,
        hysteresis_sec: Optional[float] = None,
        head_away_sec: Optional[float] = None,
        away_sec: Optional[float] = None,
        idle_active_sec: Optional[float] = None,
        low_activity_sec: Optional[float] = None,
    ):
        cfg = config or DEFAULT_ACTIVITY_CONFIG
        if (
            hysteresis_sec is not None
            or head_away_sec is not None
            or away_sec is not None
            or idle_active_sec is not None
            or low_activity_sec is not None
        ):
            self._config = WorkActivityConfig(
                recent_input_active_seconds=idle_active_sec if idle_active_sec is not None else cfg.recent_input_active_seconds,
                low_activity_entry_seconds=low_activity_sec if low_activity_sec is not None else cfg.low_activity_entry_seconds,
                attention_away_entry_seconds=head_away_sec if head_away_sec is not None else cfg.attention_away_entry_seconds,
                away_entry_seconds=away_sec if away_sec is not None else cfg.away_entry_seconds,
                state_dwell_seconds=hysteresis_sec if hysteresis_sec is not None else cfg.state_dwell_seconds,
                head_away_yaw_degrees=cfg.head_away_yaw_degrees,
            )
        else:
            self._config = cfg
        self._current_state = WorkActivityState.UNKNOWN
        self._candidate_state = WorkActivityState.UNKNOWN
        self._candidate_since: float = time.time()
        self._state_entered_at: float = time.time()

        # Cumulative tracking for absent and head-away durations
        self._absent_since: Optional[float] = None
        self._head_away_since: Optional[float] = None
        self._last_decision: Optional[WorkActivityDecision] = None

    @property
    def current_state(self) -> WorkActivityState:
        return self._current_state

    def reset(self) -> None:
        """Reset engine state for a new monitoring session."""
        now = time.time()
        self._current_state = WorkActivityState.UNKNOWN
        self._candidate_state = WorkActivityState.UNKNOWN
        self._candidate_since = now
        self._state_entered_at = now
        self._absent_since = None
        self._head_away_since = None
        self._last_decision = None

    def evaluate(
        self,
        human_state: Optional[HumanState],
        snapshot: Optional[ActivitySnapshot],
        now: Optional[float] = None,
        timestamp: Optional[float] = None,
    ) -> WorkActivityDecision:
        """Evaluate multimodal signals and return a temporal-stabilized decision."""
        if timestamp is not None:
            now = timestamp
        elif now is None:
            now = time.time()

        # 1. Check for Unknown / Missing Inputs
        if human_state is None:
            return self._commit_state(
                WorkActivityState.UNKNOWN,
                score=0.0,
                confidence=0.0,
                reasons=["INSUFFICIENT_DATA", "HUMAN_STATE_MISSING"],
                snapshot=snapshot,
                now=now,
            )

        person_present = bool(human_state.person_detected)
        head_yaw = human_state.head_yaw

        # 2. Track Presence State (AWAY)
        if not person_present:
            if self._absent_since is None:
                self._absent_since = now
            absent_duration = now - self._absent_since
            self._head_away_since = None

            if absent_duration >= self._config.away_entry_seconds:
                raw_state = WorkActivityState.AWAY
                reasons = ["PERSON_ABSENT", f"ABSENT_{int(absent_duration)}S"]
                score = 0.0
                confidence = 0.95
            else:
                # Brief absence remains in current state until threshold reached
                raw_state = self._current_state if self._current_state != WorkActivityState.UNKNOWN else WorkActivityState.AWAY
                reasons = ["PERSON_ABSENT_BRIEF"]
                score = 10.0
                confidence = 0.60

            return self._commit_state(raw_state, score, confidence, reasons, snapshot, now)

        # Person is PRESENT
        self._absent_since = None

        # 3. Track Head Orientation (ATTENTION_AWAY)
        head_is_away = False
        if head_yaw is not None and abs(head_yaw) >= self._config.head_away_yaw_degrees:
            head_is_away = True
            if self._head_away_since is None:
                self._head_away_since = now
        else:
            self._head_away_since = None

        if head_is_away and self._head_away_since is not None:
            away_duration = now - self._head_away_since
            if away_duration >= self._config.attention_away_entry_seconds:
                raw_state = WorkActivityState.ATTENTION_AWAY
                reasons = ["HEAD_TURNED_AWAY", f"YAW_{int(abs(head_yaw or 0))}DEG"]
                score = 25.0
                confidence = 0.90
                return self._commit_state(raw_state, score, confidence, reasons, snapshot, now)

        # 4. Classify ENGAGED vs OBSERVING based on workstation input
        idle_seconds = snapshot.idle_seconds if snapshot else 999.0
        reasons = []

        # Genuine input evidence: recent keystrokes, mouse moves, clicks within 15s
        if idle_seconds <= self._config.recent_input_active_seconds:
            raw_state = WorkActivityState.ENGAGED
            reasons.extend(["RECENT_INPUT", "PERSON_INTERACTING_INPUT"])
            if snapshot and snapshot.screen_activity_level in ("CHANGING", "LOW_CHANGE"):
                reasons.append("SCREEN_ACTIVE")
            # Calculate intensity score based on input recency
            score = min(100.0, max(65.0, 100.0 - idle_seconds * 2.0))
            confidence = 0.95
        else:
            # Person present and facing screen without active input -> OBSERVING
            raw_state = WorkActivityState.OBSERVING
            reasons.extend(["NO_INPUT_OBSERVING_SCREEN", "OBSERVING_SCREEN", "PERSON_READING_OBSERVING"])
            if snapshot and snapshot.screen_activity_level in ("CHANGING", "LOW_CHANGE"):
                reasons.append("SCREEN_ACTIVE_OBSERVING")
            else:
                reasons.append("SCREEN_STATIC")
            score = 45.0
            confidence = 0.85

        return self._commit_state(raw_state, score, confidence, reasons, snapshot, now)

    def _commit_state(
        self,
        raw_state: WorkActivityState,
        score: float,
        confidence: float,
        reasons: List[str],
        snapshot: Optional[ActivitySnapshot],
        now: float,
    ) -> WorkActivityDecision:
        """Apply temporal hysteresis: state must dwell for STATE_DWELL_SECONDS to switch."""
        if self._current_state == WorkActivityState.UNKNOWN:
            # Initial state locks in immediately
            self._current_state = raw_state
            self._candidate_state = raw_state
            self._state_entered_at = now
            self._candidate_since = now
        elif raw_state != self._current_state:
            # New state candidate
            if raw_state != self._candidate_state:
                self._candidate_state = raw_state
                self._candidate_since = now

            # Check hysteresis dwell confirmation
            if (now - self._candidate_since) >= self._config.state_dwell_seconds:
                self._current_state = raw_state
                self._state_entered_at = now
        else:
            # Remains in current state
            self._candidate_state = raw_state
            self._candidate_since = now

        dwell = round(now - self._state_entered_at, 1)
        decision = WorkActivityDecision(
            state=self._current_state,
            score=round(score, 1),
            confidence=round(confidence, 2),
            reason_codes=reasons,
            dwell_duration=dwell,
            snapshot=snapshot,
        )
        self._last_decision = decision
        return decision


_engine_instance: Optional[WorkActivityEngine] = None

def get_work_activity_engine() -> WorkActivityEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = WorkActivityEngine()
    return _engine_instance
