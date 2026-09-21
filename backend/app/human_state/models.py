from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HumanState(BaseModel):
    timestamp: datetime = Field(default_factory=_utc_now)
    track_id: str = Field(..., description="Anonymous track identifier")
    person_detected: bool = False
    face_detected: bool = False
    pose_detected: bool = False
    posture_status: Optional[str] = None
    posture_score: Optional[float] = None
    alertness_status: Optional[str] = None
    alertness_score: Optional[float] = None
    eye_state: Optional[str] = None
    eye_closure_duration: Optional[float] = None
    blink_rate: Optional[float] = None
    yawn_score: Optional[float] = None
    head_pitch: Optional[float] = None
    head_yaw: Optional[float] = None
    movement_score: Optional[float] = None
    risk_level: Optional[str] = None
    risk_score: Optional[float] = None
    confidence: Optional[float] = None
    blink_count: Optional[int] = 0
    longest_eye_closure: Optional[float] = 0.0
    valid_eye_tracking_seconds: Optional[float] = 0.0
    baseline_source: Optional[str] = "BUILT_IN"
    baseline_confidence: Optional[float] = 0.85
    head_roll: Optional[float] = None
    neck_inclination: Optional[float] = None
    shoulder_tilt: Optional[float] = None
    torso_inclination: Optional[float] = None
    activity_state: Optional[str] = "UNKNOWN"
    activity_score: Optional[float] = None
    activity_confidence: Optional[float] = None
    activity_reason_codes: Optional[list[str]] = None
    idle_seconds: Optional[float] = 0.0
    keyboard_activity_count: Optional[int] = 0
    mouse_activity_count: Optional[int] = 0
    mouse_click_count: Optional[int] = 0
    scroll_count: Optional[int] = 0
    screen_activity_level: Optional[str] = "STATIC"
    screen_change_score: Optional[float] = 0.0

    model_config = {"arbitrary_types_allowed": True}

    @property
    def is_alert(self) -> bool:
        return self.risk_level in ("HIGH", "CRITICAL") if self.risk_level else False

    @property
    def is_safe(self) -> bool:
        return self.risk_level in ("LOW",) if self.risk_level else True


class HumanStateCreate(BaseModel):
    track_id: str
    person_detected: bool = False
    face_detected: bool = False
    pose_detected: bool = False
    posture_status: Optional[str] = None
    posture_score: Optional[float] = None
    alertness_status: Optional[str] = None
    alertness_score: Optional[float] = None
    eye_state: Optional[str] = None
    eye_closure_duration: Optional[float] = None
    blink_rate: Optional[float] = None
    yawn_score: Optional[float] = None
    head_pitch: Optional[float] = None
    head_yaw: Optional[float] = None
    movement_score: Optional[float] = None
    risk_level: Optional[str] = None
    risk_score: Optional[float] = None
    confidence: Optional[float] = None
    blink_count: Optional[int] = 0
    longest_eye_closure: Optional[float] = 0.0
    valid_eye_tracking_seconds: Optional[float] = 0.0
    baseline_source: Optional[str] = "BUILT_IN"
    baseline_confidence: Optional[float] = 0.85
    head_roll: Optional[float] = None
    neck_inclination: Optional[float] = None
    shoulder_tilt: Optional[float] = None
    torso_inclination: Optional[float] = None
    activity_state: Optional[str] = "UNKNOWN"
    activity_score: Optional[float] = None
    activity_confidence: Optional[float] = None
    activity_reason_codes: Optional[list[str]] = None
    idle_seconds: Optional[float] = 0.0
    keyboard_activity_count: Optional[int] = 0
    mouse_activity_count: Optional[int] = 0
    mouse_click_count: Optional[int] = 0
    scroll_count: Optional[int] = 0
    screen_activity_level: Optional[str] = "STATIC"
    screen_change_score: Optional[float] = 0.0
