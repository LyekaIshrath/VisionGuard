"""VisionGuard Mission 07: Centralized Alert Policy Configuration.

Contains engineering defaults for anti-spam, independent cooldowns,
and deterministic calm message phrasing.
"""

from __future__ import annotations

from typing import Dict, Tuple, Optional
from pydantic import BaseModel, Field

from app.intelligence.risk_models import RiskCategory, RiskLevel
from app.alerts.models import AlertPriority

# Authoritative deterministic calm message templates (Phase 6)
CALM_ALERT_MESSAGES: Dict[Tuple[RiskCategory, RiskLevel], str] = {
    (RiskCategory.POSTURE, RiskLevel.MODERATE): (
        "Your posture has been off for a while. Consider adjusting your sitting position."
    ),
    (RiskCategory.POSTURE, RiskLevel.HIGH): (
        "Your posture needs attention. Please adjust your sitting position."
    ),
    (RiskCategory.ALERTNESS, RiskLevel.MODERATE): (
        "You appear less alert. Consider taking a short break."
    ),
    (RiskCategory.ALERTNESS, RiskLevel.HIGH): (
        "Your alertness appears reduced. Please consider taking a break."
    ),
}


class AlertPolicyConfig(BaseModel):
    """Centralized engineering thresholds for anti-spam and cooldown timing."""
    # Independent voice cooldowns (Phase 3 defaults)
    posture_voice_cooldown_sec: float = Field(default=60.0, description="Minimum seconds between spoken posture alerts")
    alertness_voice_cooldown_sec: float = Field(default=30.0, description="Minimum seconds between spoken alertness alerts")

    # Browser notification cooldown per category
    notification_cooldown_sec: float = Field(default=30.0, description="Minimum seconds between browser notifications per category")

    # Maximum queued voice alerts
    max_voice_queue_size: int = Field(default=5, description="Maximum pending voice alerts allowed")

    def get_voice_cooldown(self, category: RiskCategory) -> float:
        if category == RiskCategory.POSTURE:
            return self.posture_voice_cooldown_sec
        return self.alertness_voice_cooldown_sec

    def get_message(self, category: RiskCategory, level: RiskLevel, default_msg: Optional[str] = None) -> str:
        msg = CALM_ALERT_MESSAGES.get((category, level))
        if msg:
            return msg
        return default_msg or f"{category.value} {level.value} alert"

    def get_priority(self, level: RiskLevel) -> AlertPriority:
        if level == RiskLevel.HIGH:
            return AlertPriority.CRITICAL
        if level == RiskLevel.MODERATE:
            return AlertPriority.IMPORTANT
        return AlertPriority.NORMAL


DEFAULT_ALERT_POLICY = AlertPolicyConfig()
