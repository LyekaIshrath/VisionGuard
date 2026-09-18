"""VisionGuard Mission 07: Centralized Alert Policy Configuration.

Contains engineering defaults for anti-spam, independent cooldowns,
and deterministic calm message phrasing in English and Tamil.
"""

from __future__ import annotations

from typing import Dict, Tuple, Optional
from pydantic import BaseModel, Field

from app.intelligence.risk_models import RiskCategory, RiskLevel
from app.alerts.models import AlertPriority

# Authoritative deterministic calm message templates (English)
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

CALM_ALERT_MESSAGES_EN = CALM_ALERT_MESSAGES

# Canonical deterministic wellness/safety intervention messages (Tamil Unicode)
CALM_ALERT_MESSAGES_TA: Dict[Tuple[RiskCategory, RiskLevel], str] = {
    (RiskCategory.POSTURE, RiskLevel.MODERATE): (
        "உங்கள் அமரும் தோரணையை சரிசெய்யவும்."
    ),
    (RiskCategory.POSTURE, RiskLevel.HIGH): (
        "தோரணையில் கவனம் தேவை. தயவுசெய்து நேராக உட்காரவும்."
    ),
    (RiskCategory.ALERTNESS, RiskLevel.MODERATE): (
        "கவனம் தேவை. கண்களை சிமிட்டி புத்துணர்ச்சி பெறவும்."
    ),
    (RiskCategory.ALERTNESS, RiskLevel.HIGH): (
        "சோர்வு கண்டறியப்பட்டது. தயவுசெய்து சிறிது நேரம் ஓய்வெடுக்கவும்."
    ),
}

# Canonical fixed-alert audio identifiers for pre-rendered assets
ALERT_AUDIO_KEYS: Dict[Tuple[RiskCategory, RiskLevel], str] = {
    (RiskCategory.POSTURE, RiskLevel.MODERATE): "posture_moderate",
    (RiskCategory.POSTURE, RiskLevel.HIGH): "posture_high",
    (RiskCategory.ALERTNESS, RiskLevel.MODERATE): "alertness_moderate",
    (RiskCategory.ALERTNESS, RiskLevel.HIGH): "alertness_high",
}


class AlertPolicyConfig(BaseModel):
    """Centralized engineering thresholds for anti-spam, cooldown timing, and natural alert routing."""
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

    def get_message(
        self,
        category: RiskCategory,
        level: RiskLevel,
        default_msg: Optional[str] = None,
        language: str = "en"
    ) -> str:
        """Return canonical wellness/safety phrasing in the requested language."""
        if language == "ta":
            msg = CALM_ALERT_MESSAGES_TA.get((category, level))
            if msg:
                return msg
        msg = CALM_ALERT_MESSAGES_EN.get((category, level))
        if msg:
            return msg
        return default_msg or f"{category.value} {level.value} alert"

    def get_audio_key(self, category: RiskCategory, level: RiskLevel) -> Optional[str]:
        """Return the pre-rendered audio asset key for fixed alerts."""
        return ALERT_AUDIO_KEYS.get((category, level))

    def get_priority(self, level: RiskLevel) -> AlertPriority:
        if level == RiskLevel.HIGH:
            return AlertPriority.CRITICAL
        if level == RiskLevel.MODERATE:
            return AlertPriority.IMPORTANT
        return AlertPriority.NORMAL


DEFAULT_ALERT_POLICY = AlertPolicyConfig()
