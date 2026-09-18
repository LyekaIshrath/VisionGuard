"""VisionGuard Mission 05 & 07: Alert and Intervention Models."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from app.intelligence.risk_models import RiskLevel, RiskCategory, RiskReasonCode


class EventStatus(str, Enum):
    """Lifecycle status of a risk event."""
    STARTED = "STARTED"
    ONGOING = "ONGOING"
    RESOLVED = "RESOLVED"


class InterventionType(str, Enum):
    """Channel through which an intervention is delivered."""
    IN_APP = "IN_APP"
    BROWSER_NOTIFICATION = "BROWSER_NOTIFICATION"
    VOICE = "VOICE"


class AlertChannel(str, Enum):
    """Delivery channels for alerts."""
    IN_APP = "IN_APP"
    BROWSER_NOTIFICATION = "BROWSER_NOTIFICATION"
    VOICE = "VOICE"


class AlertPriority(str, Enum):
    """Priority classification for alerts."""
    NORMAL = "NORMAL"
    IMPORTANT = "IMPORTANT"
    CRITICAL = "CRITICAL"


class RiskEvent(BaseModel):
    """Typed event emitted on meaningful risk escalation or resolution.

    Strict privacy: derived metrics only, no frames, no landmarks.
    """
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    category: RiskCategory
    status: EventStatus
    risk_level: RiskLevel
    risk_score: Optional[float] = None
    message: str
    reason_codes: List[RiskReasonCode] = Field(default_factory=list)
    duration_sec: float = 0.0


class Intervention(BaseModel):
    """Structured actionable advice delivered to the user."""
    intervention_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    category: RiskCategory
    level: RiskLevel
    title: str
    message: str
    type: InterventionType = InterventionType.IN_APP


class AlertAction(BaseModel):
    """Actionable alert dispatch directive determined by AlertOrchestrator.

    Strict privacy: zero camera, face, or pose landmark data.
    """
    alert_id: str = Field(..., description="Unique alert directive identifier")
    intervention_id: str = Field(..., description="Associated intervention identifier")
    category: RiskCategory
    risk_level: RiskLevel
    channel: AlertChannel
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    priority: AlertPriority = AlertPriority.NORMAL
    requires_acknowledgement: bool = False
