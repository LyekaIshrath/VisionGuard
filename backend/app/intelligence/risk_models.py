"""VisionGuard Mission 05: Typed Risk Models and Enums."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Authoritative non-medical risk levels."""
    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class RiskCategory(str, Enum):
    """Independent risk domains."""
    POSTURE = "POSTURE"
    ALERTNESS = "ALERTNESS"
    COMBINED = "COMBINED"
    SYSTEM = "SYSTEM"


class RiskReasonCode(str, Enum):
    """Interpretable, non-medical reason codes for active risk."""
    SUSTAINED_SLOUCH = "SUSTAINED_SLOUCH"
    SUSTAINED_FORWARD_LEAN = "SUSTAINED_FORWARD_LEAN"
    SUSTAINED_LEFT_LEAN = "SUSTAINED_LEFT_LEAN"
    SUSTAINED_RIGHT_LEAN = "SUSTAINED_RIGHT_LEAN"
    POSTURE_DEVIATION = "POSTURE_DEVIATION"

    POSSIBLE_DROWSINESS = "POSSIBLE_DROWSINESS"
    PROLONGED_EYE_CLOSURE = "PROLONGED_EYE_CLOSURE"
    ELEVATED_ALERTNESS_EVIDENCE = "ELEVATED_ALERTNESS_EVIDENCE"

    INSUFFICIENT_OBSERVATION = "INSUFFICIENT_OBSERVATION"


class DomainRiskState(BaseModel):
    """State for a single risk domain (e.g. Posture or Alertness)."""
    category: RiskCategory
    level: RiskLevel
    score: Optional[float] = Field(None, ge=0.0, le=100.0)
    is_valid: bool = True
    active_duration_sec: float = 0.0
    reasons: List[RiskReasonCode] = Field(default_factory=list)


class OverallRiskState(BaseModel):
    """Fused overall risk state across all evaluated domains."""
    level: RiskLevel
    score: Optional[float] = Field(None, ge=0.0, le=100.0)
    posture_risk: DomainRiskState
    alertness_risk: DomainRiskState
    dominant_category: Optional[RiskCategory] = None
    active_reasons: List[RiskReasonCode] = Field(default_factory=list)
    confidence: float = 0.0
