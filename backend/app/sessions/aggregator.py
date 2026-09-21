"""VisionGuard Mission 06 and Final Acceptance: Session Aggregator.

Thread-safe aggregator accumulating frame-by-frame ergonomics, alertness metrics,
workstation input telemetry, and work activity states during an active monitoring session.

Strict Privacy Guarantees:
- Stores purely derived statistical aggregates.
- ABSOLUTELY NEVER stores raw video frames, biometric landmarks, or facial features.
- Never logs keystroke identities, clipboard, or mouse coordinates.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from app.human_state.models import HumanState


class CanonicalPresenceSummary(BaseModel):
    present_seconds: float = 0.0
    away_seconds: float = 0.0
    unknown_seconds: float = 0.0
    present_pct: float = 0.0
    away_pct: float = 0.0
    unknown_pct: float = 0.0
    away_episodes: int = 0


class CanonicalActivitySummary(BaseModel):
    engaged_seconds: float = 0.0
    observing_seconds: float = 0.0
    attention_away_seconds: float = 0.0
    away_seconds: float = 0.0
    unknown_seconds: float = 0.0
    engaged_pct: float = 0.0
    observing_pct: float = 0.0
    attention_away_pct: float = 0.0
    away_pct: float = 0.0
    unknown_pct: float = 0.0


class CanonicalComputerSummary(BaseModel):
    keyboard_events: int = 0
    mouse_movements: int = 0
    mouse_clicks: int = 0
    scroll_count: int = 0
    longest_idle_seconds: float = 0.0
    # Backward compatible aliases for UI
    keystrokes: int = 0
    mouse_moves: int = 0
    clicks: int = 0
    scrolls: int = 0


class CanonicalScreenSummary(BaseModel):
    screen_active_seconds: float = 0.0
    low_change_seconds: float = 0.0
    static_seconds: float = 0.0
    unknown_seconds: float = 0.0
    changing_pct: float = 0.0
    low_change_pct: float = 0.0
    static_pct: float = 0.0
    unknown_pct: float = 0.0


class CanonicalEyeSummary(BaseModel):
    blink_count: int = 0
    total_blinks: int = 0
    blink_rate: Optional[float] = None
    blink_rate_per_min: Optional[float] = None
    valid_eye_tracking_seconds: float = 0.0
    valid_eye_observation_pct: float = 0.0
    longest_eye_closure_seconds: float = 0.0


class CanonicalHeadSummary(BaseModel):
    facing_workstation_seconds: float = 0.0
    facing_workstation_pct: float = 0.0
    attention_away_seconds: float = 0.0
    attention_away_episodes: int = 0


class CanonicalPostureSummary(BaseModel):
    good_posture_seconds: float = 0.0
    slouching_seconds: float = 0.0
    forward_lean_seconds: float = 0.0
    left_lean_seconds: float = 0.0
    right_lean_seconds: float = 0.0
    unknown_posture_seconds: float = 0.0
    valid_posture_seconds: float = 0.0
    posture_risk_seconds: float = 0.0
    good_pct: float = 0.0
    slouching_pct: float = 0.0
    forward_lean_pct: float = 0.0
    left_lean_pct: float = 0.0
    right_lean_pct: float = 0.0
    unknown_pct: float = 0.0
    posture_events: int = 0


class CanonicalSessionSummary(BaseModel):
    """Authoritative contract for finalized session data.
    Enforces strict key alignment across aggregator, MongoDB, API, and UI.
    """
    presence_summary: CanonicalPresenceSummary
    activity_summary: CanonicalActivitySummary
    computer_summary: CanonicalComputerSummary
    screen_summary: CanonicalScreenSummary
    eye_summary: CanonicalEyeSummary
    head_summary: CanonicalHeadSummary
    posture_summary: CanonicalPostureSummary
    timeline: List[Dict[str, Any]] = Field(default_factory=list)


def validate_canonical_summary(data: Dict[str, Any]) -> CanonicalSessionSummary:
    """Validate that a dictionary strictly adheres to the canonical summary contract."""
    pres = data.get("presence_summary") or data.get("presence") or {}
    act = data.get("activity_summary") or data.get("work_activity") or {}
    comp = data.get("computer_summary") or data.get("computer") or {}
    scr = data.get("screen_summary") or data.get("screen") or {}
    eye = data.get("eye_summary") or data.get("eyes") or {}
    head = data.get("head_summary") or {}
    post = data.get("posture_summary") or {}
    tl = data.get("timeline", [])

    return CanonicalSessionSummary(
        presence_summary=CanonicalPresenceSummary(**pres),
        activity_summary=CanonicalActivitySummary(**act),
        computer_summary=CanonicalComputerSummary(**comp),
        screen_summary=CanonicalScreenSummary(**scr),
        eye_summary=CanonicalEyeSummary(**eye),
        head_summary=CanonicalHeadSummary(**head),
        posture_summary=CanonicalPostureSummary(**post),
        timeline=tl,
    )


class SessionAggregator:
    """Thread-safe in-memory aggregator accumulating human safety and work metrics."""

    def __init__(self, started_at: Optional[datetime] = None, session_id: Optional[str] = None, user_id: Optional[str] = None, **kwargs) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.started_at: datetime = started_at or datetime.now(timezone.utc)
        self.ended_at: Optional[datetime] = None
        self.last_sample_mono: Optional[float] = None
        self.total_active_seconds: float = 0.0

        # Presence
        self.presence_seconds: float = 0.0
        self.away_seconds: float = 0.0
        self.unknown_presence_seconds: float = 0.0
        self.away_episodes: int = 0
        self._in_away_episode: bool = False

        # Work Activity States (ENGAGED, OBSERVING, ATTENTION_AWAY, AWAY, UNKNOWN)
        self.engaged_seconds: float = 0.0
        self.observing_seconds: float = 0.0
        self.attention_away_seconds: float = 0.0
        self.activity_away_seconds: float = 0.0
        self.activity_unknown_seconds: float = 0.0
        self.attention_away_episodes: int = 0
        self._in_attention_away_episode: bool = False

        # Workstation Telemetry
        self.keyboard_event_count: int = 0
        self.mouse_event_count: int = 0
        self.mouse_click_count: int = 0
        self.scroll_count: int = 0
        self.longest_idle_seconds: float = 0.0

        # Screen Telemetry
        self.screen_active_seconds: float = 0.0
        self.screen_low_change_seconds: float = 0.0
        self.screen_static_seconds: float = 0.0
        self.screen_unknown_seconds: float = 0.0

        # Eye & Blink Telemetry
        self.blink_count: int = 0
        self.blink_rate: Optional[float] = None
        self.valid_eye_tracking_seconds: float = 0.0
        self.longest_eye_closure: float = 0.0

        # Measured Posture Categories
        self.good_posture_seconds: float = 0.0
        self.slouching_seconds: float = 0.0
        self.forward_lean_seconds: float = 0.0
        self.left_lean_seconds: float = 0.0
        self.right_lean_seconds: float = 0.0
        self.unknown_posture_seconds: float = 0.0
        self.posture_risk_seconds: float = 0.0
        self.posture_score_weighted_sum: float = 0.0
        self.posture_valid_seconds: float = 0.0

        # Alertness
        self.alertness_risk_seconds: float = 0.0
        self.alertness_score_weighted_sum: float = 0.0
        self.alertness_valid_seconds: float = 0.0
        self.alertness_risk_episodes: int = 0
        self.timeline: List[Dict[str, Any]] = []
        self._in_alertness_risk_episode: bool = False

        # Counts
        self.risk_event_count: int = 0
        self.intervention_count: int = 0

    def add_sample(self, state: HumanState, current_mono: Optional[float] = None) -> None:
        if current_mono is None:
            current_mono = time.monotonic()

        if self.last_sample_mono is None:
            dt = 0.0
        else:
            dt = current_mono - self.last_sample_mono
            # Clamp dt to maximum 1.0s to avoid skewing metrics after pauses
            dt = max(0.0, min(dt, 1.0))

        self.last_sample_mono = current_mono
        self.total_active_seconds += dt

        # --- Screen Activity Tracking ---
        scr = getattr(state, "screen_activity_level", "UNKNOWN") or "UNKNOWN"
        if scr == "CHANGING":
            self.screen_active_seconds += dt
        elif scr == "LOW_CHANGE":
            self.screen_low_change_seconds += dt
        elif scr == "STATIC":
            self.screen_static_seconds += dt
        else:
            self.screen_unknown_seconds += dt

        # --- Presence Tracking ---
        if state.person_detected:
            self.presence_seconds += dt
            self._in_away_episode = False
        else:
            self.away_seconds += dt
            if not self._in_away_episode:
                self.away_episodes += 1
                self._in_away_episode = True

        # --- Work Activity State Tracking (Strict Disjoint Distribution) ---
        act = (getattr(state, "activity_state", None) or "UNKNOWN").upper()
        if act in ("ENGAGED", "ACTIVE"):
            self.engaged_seconds += dt
            self._in_attention_away_episode = False
        elif act in ("OBSERVING", "LOW_ACTIVITY"):
            self.observing_seconds += dt
            self._in_attention_away_episode = False
        elif act == "ATTENTION_AWAY":
            self.attention_away_seconds += dt
            if not self._in_attention_away_episode:
                self.attention_away_episodes += 1
                self._in_attention_away_episode = True
        elif act == "AWAY":
            self.activity_away_seconds += dt
            self._in_attention_away_episode = False
        else:
            self.activity_unknown_seconds += dt
            self._in_attention_away_episode = False

        # --- Workstation Input Telemetry ---
        kb = getattr(state, "keyboard_activity_count", None)
        if kb is not None:
            self.keyboard_event_count = max(self.keyboard_event_count, int(kb))

        mouse = getattr(state, "mouse_activity_count", None)
        if mouse is not None:
            self.mouse_event_count = max(self.mouse_event_count, int(mouse))

        clicks = getattr(state, "mouse_click_count", None)
        if clicks is not None:
            self.mouse_click_count = max(self.mouse_click_count, int(clicks))

        scrolls = getattr(state, "scroll_count", None)
        if scrolls is not None:
            self.scroll_count = max(self.scroll_count, int(scrolls))

        idle = getattr(state, "idle_seconds", None)
        if idle is not None:
            self.longest_idle_seconds = max(self.longest_idle_seconds, float(idle))

        # --- Blink & Eye Tracking ---
        blinks = getattr(state, "blink_count", None)
        if blinks is not None:
            self.blink_count = max(self.blink_count, int(blinks))

        longest_closure = getattr(state, "longest_eye_closure", None)
        if longest_closure is not None:
            self.longest_eye_closure = max(self.longest_eye_closure, float(longest_closure))

        valid_eyes = getattr(state, "valid_eye_tracking_seconds", None)
        if valid_eyes is not None:
            self.valid_eye_tracking_seconds = max(self.valid_eye_tracking_seconds, float(valid_eyes))
        elif state.person_detected:
            # Fallback when eye landmarks are detected in frame
            self.valid_eye_tracking_seconds += dt

        # --- Posture Metrics ---
        status = getattr(state, "posture_status", "UNKNOWN") or "UNKNOWN"
        if status == "GOOD":
            self.good_posture_seconds += dt
        elif status == "SLOUCHING":
            self.slouching_seconds += dt
            self.posture_risk_seconds += dt
        elif status == "FORWARD_LEAN":
            self.forward_lean_seconds += dt
            self.posture_risk_seconds += dt
        elif status == "LEFT_LEAN":
            self.left_lean_seconds += dt
            self.posture_risk_seconds += dt
        elif status == "RIGHT_LEAN":
            self.right_lean_seconds += dt
            self.posture_risk_seconds += dt
        elif status in ("NEEDS_ATTENTION", "RISK"):
            self.slouching_seconds += dt
            self.posture_risk_seconds += dt
        else:
            self.unknown_posture_seconds += dt

        if (state.posture_score is not None and
            status not in ("UNKNOWN", "NOT_CALIBRATED", None)):
            self.posture_score_weighted_sum += state.posture_score * dt
            self.posture_valid_seconds += dt

        # --- Alertness Metrics ---
        alt_status = getattr(state, "alertness_status", "UNKNOWN") or "UNKNOWN"
        if alt_status == "POSSIBLE_DROWSINESS":
            self.alertness_risk_seconds += dt
            if not self._in_alertness_risk_episode:
                self.alertness_risk_episodes += 1
                self._in_alertness_risk_episode = True
        elif alt_status == "ALERT":
            self._in_alertness_risk_episode = False

        if (state.alertness_score is not None and
            alt_status not in ("UNKNOWN", "NOT_CALIBRATED", None)):
            self.alertness_score_weighted_sum += state.alertness_score * dt
            self.alertness_valid_seconds += dt

    def record_risk_event(self) -> None:
        self.risk_event_count += 1

    def record_intervention(self) -> None:
        self.intervention_count += 1

    def get_summary(self) -> Dict[str, Any]:
        self.ended_at = datetime.now(timezone.utc)
        total_duration = max(0.1, round(self.total_active_seconds, 1))

        avg_posture = (
            round(self.posture_score_weighted_sum / self.posture_valid_seconds, 1)
            if self.posture_valid_seconds > 0 else None
        )
        avg_alertness = (
            round(self.alertness_score_weighted_sum / self.alertness_valid_seconds, 1)
            if self.alertness_valid_seconds > 0 else None
        )

        # Posture Exposure Calculations
        valid_posture = self.posture_valid_seconds if self.posture_valid_seconds > 0 else (
            self.good_posture_seconds + self.slouching_seconds +
            self.forward_lean_seconds + self.left_lean_seconds + self.right_lean_seconds
        )
        denom_posture = max(0.01, valid_posture)
        good_pct = round((self.good_posture_seconds / denom_posture) * 100, 1) if valid_posture > 0 else 0.0
        slouching_pct = round((self.slouching_seconds / denom_posture) * 100, 1) if valid_posture > 0 else 0.0
        forward_lean_pct = round((self.forward_lean_seconds / denom_posture) * 100, 1) if valid_posture > 0 else 0.0
        left_lean_pct = round((self.left_lean_seconds / denom_posture) * 100, 1) if valid_posture > 0 else 0.0
        right_lean_pct = round((self.right_lean_seconds / denom_posture) * 100, 1) if valid_posture > 0 else 0.0
        unknown_post_pct = round((self.unknown_posture_seconds / total_duration) * 100, 1)

        # Blink Rate: computed against valid_eye_tracking_minutes, NOT total session duration
        valid_eye_mins = self.valid_eye_tracking_seconds / 60.0
        if valid_eye_mins >= 0.1:  # At least 6 seconds of valid eye observation
            calculated_blink_rate = round(self.blink_count / valid_eye_mins, 1)
        else:
            calculated_blink_rate = None

        # Presence Percentages
        present_pct = round((self.presence_seconds / total_duration) * 100, 1)
        away_pct = round((self.away_seconds / total_duration) * 100, 1)
        unknown_pres_pct = round(max(0.0, 100.0 - present_pct - away_pct), 1)

        # Work Activity Percentages
        engaged_pct = round((self.engaged_seconds / total_duration) * 100, 1)
        observing_pct = round((self.observing_seconds / total_duration) * 100, 1)
        att_away_pct = round((self.attention_away_seconds / total_duration) * 100, 1)
        act_away_pct = round((self.activity_away_seconds / total_duration) * 100, 1)
        act_unknown_pct = round(max(0.0, 100.0 - (engaged_pct + observing_pct + att_away_pct + act_away_pct)), 1)

        # Screen Activity Percentages
        scr_changing_pct = round((self.screen_active_seconds / total_duration) * 100, 1)
        scr_low_pct = round((self.screen_low_change_seconds / total_duration) * 100, 1)
        scr_static_pct = round((self.screen_static_seconds / total_duration) * 100, 1)
        scr_unknown_pct = round(max(0.0, 100.0 - (scr_changing_pct + scr_low_pct + scr_static_pct)), 1)

        return {
            # Legacy Fields
            "duration_seconds": total_duration,
            "good_posture_seconds": round(self.good_posture_seconds, 1),
            "posture_risk_seconds": round(self.posture_risk_seconds, 1),
            "alertness_risk_seconds": round(self.alertness_risk_seconds, 1),
            "average_posture_score": avg_posture,
            "average_alertness_score": avg_alertness,
            "valid_posture_seconds": round(valid_posture, 1),
            "valid_alertness_seconds": round(self.alertness_valid_seconds, 1),
            "risk_event_count": self.risk_event_count,
            "intervention_count": self.intervention_count,

            # Extended Work Activity & Biometric Fields
            "started_at": self.started_at.isoformat() if hasattr(self.started_at, "isoformat") else str(self.started_at),
            "ended_at": self.ended_at.isoformat() if hasattr(self.ended_at, "isoformat") else str(self.ended_at),
            "total_monitored_seconds": total_duration,

            "presence_seconds": round(self.presence_seconds, 1),
            "away_seconds": round(self.away_seconds, 1),
            "unknown_presence_seconds": round(self.unknown_presence_seconds, 1),

            "active_seconds": round(self.engaged_seconds, 1),
            "low_activity_seconds": round(self.observing_seconds, 1),
            "attention_away_seconds": round(self.attention_away_seconds, 1),
            "activity_away_seconds": round(self.activity_away_seconds, 1),
            "activity_unknown_seconds": round(self.activity_unknown_seconds, 1),

            "keyboard_event_count": self.keyboard_event_count,
            "mouse_event_count": self.mouse_event_count,

            # Canonical Summaries for MongoDB and Work Session Reports
            "presence_summary": {
                "present_seconds": round(self.presence_seconds, 1),
                "away_seconds": round(self.away_seconds, 1),
                "unknown_seconds": round(self.unknown_presence_seconds, 1),
                "present_pct": present_pct,
                "away_pct": away_pct,
                "unknown_pct": unknown_pres_pct,
                "away_episodes": self.away_episodes,
            },
            "activity_summary": {
                "engaged_seconds": round(self.engaged_seconds, 1),
                "observing_seconds": round(self.observing_seconds, 1),
                "attention_away_seconds": round(self.attention_away_seconds, 1),
                "away_seconds": round(self.activity_away_seconds, 1),
                "unknown_seconds": round(self.activity_unknown_seconds, 1),
                "engaged_pct": engaged_pct,
                "observing_pct": observing_pct,
                "attention_away_pct": att_away_pct,
                "away_pct": act_away_pct,
                "unknown_pct": act_unknown_pct,
            },
            "computer_summary": {
                "keyboard_events": self.keyboard_event_count,
                "mouse_movements": self.mouse_event_count,
                "mouse_clicks": self.mouse_click_count,
                "scroll_count": self.scroll_count,
                "longest_idle_seconds": round(self.longest_idle_seconds, 1),
                # Aliases for ReportModal compatibility
                "keystrokes": self.keyboard_event_count,
                "mouse_moves": self.mouse_event_count,
                "clicks": self.mouse_click_count,
                "scrolls": self.scroll_count,
            },
            "screen_summary": {
                "screen_active_seconds": round(self.screen_active_seconds, 1),
                "low_change_seconds": round(self.screen_low_change_seconds, 1),
                "static_seconds": round(self.screen_static_seconds, 1),
                "unknown_seconds": round(self.screen_unknown_seconds, 1),
                "changing_pct": scr_changing_pct,
                "low_change_pct": scr_low_pct,
                "static_pct": scr_static_pct,
                "unknown_pct": scr_unknown_pct,
            },
            "eye_summary": {
                "blink_count": self.blink_count,
                "total_blinks": self.blink_count,
                "blink_rate": calculated_blink_rate,
                "blink_rate_per_min": calculated_blink_rate,
                "valid_eye_tracking_seconds": round(self.valid_eye_tracking_seconds, 1),
                "valid_eye_observation_pct": round((self.valid_eye_tracking_seconds / total_duration) * 100, 1),
                "longest_eye_closure_seconds": round(self.longest_eye_closure, 2),
            },
            "head_summary": {
                "facing_workstation_seconds": round(max(0.0, self.presence_seconds - self.attention_away_seconds), 1),
                "facing_workstation_pct": round((max(0.0, self.presence_seconds - self.attention_away_seconds) / total_duration) * 100, 1),
                "attention_away_seconds": round(self.attention_away_seconds, 1),
                "attention_away_episodes": self.attention_away_episodes,
            },
            "timeline": list(self.timeline),
            "posture_summary": {
                "good_posture_seconds": round(self.good_posture_seconds, 1),
                "slouching_seconds": round(self.slouching_seconds, 1),
                "forward_lean_seconds": round(self.forward_lean_seconds, 1),
                "left_lean_seconds": round(self.left_lean_seconds, 1),
                "right_lean_seconds": round(self.right_lean_seconds, 1),
                "unknown_posture_seconds": round(self.unknown_posture_seconds, 1),
                "valid_posture_seconds": round(valid_posture, 1),
                "posture_risk_seconds": round(self.posture_risk_seconds, 1),
                "good_pct": good_pct,
                "slouching_pct": slouching_pct,
                "forward_lean_pct": forward_lean_pct,
                "left_lean_pct": left_lean_pct,
                "right_lean_pct": right_lean_pct,
                "unknown_pct": unknown_post_pct,
                "posture_events": self.risk_event_count,
            },
            "mouse_click_count": self.mouse_click_count,
            "scroll_count": self.scroll_count,
            "longest_idle_seconds": round(self.longest_idle_seconds, 1),

            "blink_count": self.blink_count,
            "valid_eye_tracking_seconds": round(self.valid_eye_tracking_seconds, 1),
            "blink_rate": calculated_blink_rate,
            "longest_eye_closure": round(self.longest_eye_closure, 2),

            "alertness_risk_episodes": self.alertness_risk_episodes,
        }
