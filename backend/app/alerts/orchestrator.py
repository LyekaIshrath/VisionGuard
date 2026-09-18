"""VisionGuard Mission 07: Alert Orchestrator.

Strictly downstream coordination of alert actions (in-app, browser, voice).
Enforces anti-spam, independent cooldowns, escalation rules, and acknowledgement.
NEVER accesses camera frames or runs MediaPipe inference.
"""

from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone

from app.intelligence.risk_models import RiskCategory, RiskLevel
from app.alerts.models import (
    Intervention,
    AlertAction,
    AlertChannel,
    AlertPriority,
    EventStatus,
    RiskEvent,
)
from app.alerts.policy import AlertPolicyConfig, DEFAULT_ALERT_POLICY


class AlertOrchestrator:
    """
    Downstream decision engine that determines channel delivery eligibility for interventions.
    Actual execution of speech and browser notifications happens client-side in the browser.
    """

    def __init__(self, policy: Optional[AlertPolicyConfig] = None):
        self.policy = policy or DEFAULT_ALERT_POLICY

        # Monotonic timestamp of last dispatched alert per channel and category
        self._last_voice_time: Dict[RiskCategory, float] = {}
        self._last_notification_time: Dict[RiskCategory, float] = {}

        # Tracking active levels to implement escalation bypass
        self._last_category_level: Dict[RiskCategory, RiskLevel] = {}

        # Set of dispatched intervention IDs to prevent repeat delivery
        self._dispatched_interventions: Set[str] = set()

        # Set of acknowledged intervention IDs
        self._acknowledged_interventions: Set[str] = set()

        # Currently active intervention per category
        self._active_interventions: Dict[RiskCategory, Optional[Intervention]] = {
            RiskCategory.POSTURE: None,
            RiskCategory.ALERTNESS: None,
            RiskCategory.COMBINED: None,
            RiskCategory.SYSTEM: None,
        }

    def reset_session(self) -> None:
        """Resets transient orchestrator state on monitoring start/stop/signout."""
        self._last_voice_time.clear()
        self._last_notification_time.clear()
        self._last_category_level.clear()
        self._dispatched_interventions.clear()
        self._acknowledged_interventions.clear()
        for k in self._active_interventions:
            self._active_interventions[k] = None

    def acknowledge_alert(self, intervention_id: str) -> bool:
        """
        Records user acknowledgement of an alert.
        Hides UI presentation without modifying physical RiskEngine state.
        """
        self._acknowledged_interventions.add(intervention_id)
        return True

    def is_acknowledged(self, intervention_id: str) -> bool:
        return intervention_id in self._acknowledged_interventions

    def handle_resolution(self, category: RiskCategory) -> None:
        """
        Clears active alert state upon event resolution.
        Does not speak repeated recovery announcements.
        """
        self._active_interventions[category] = None
        self._last_category_level[category] = RiskLevel.LOW

    def evaluate_intervention(
        self,
        intervention: Intervention,
        voice_alerts_enabled: bool = False,
        browser_notifications_enabled: bool = False,
        quiet_mode_enabled: bool = False,
        current_mono: Optional[float] = None,
    ) -> List[AlertAction]:
        """
        Evaluates an incoming Intervention against the policy and user preferences.
        Returns a list of AlertAction directives for the client.
        """
        if current_mono is None:
            current_mono = time.monotonic()

        category = intervention.category
        level = intervention.level

        # UNKNOWN or LOW produce NO audible/browser alerts
        if level in (RiskLevel.UNKNOWN, RiskLevel.LOW):
            self.handle_resolution(category)
            return []

        # Track active intervention
        self._active_interventions[category] = intervention

        actions: List[AlertAction] = []
        msg = self.policy.get_message(category, level, default_msg=intervention.message)
        priority = self.policy.get_priority(level)
        requires_ack = (level == RiskLevel.HIGH)

        # 1. IN_APP Channel: Always eligible unless already acknowledged
        if not self.is_acknowledged(intervention.intervention_id):
            actions.append(
                AlertAction(
                    alert_id=f"alert-inapp-{uuid.uuid4().hex[:8]}",
                    intervention_id=intervention.intervention_id,
                    category=category,
                    risk_level=level,
                    channel=AlertChannel.IN_APP,
                    message=msg,
                    priority=priority,
                    requires_acknowledgement=requires_ack,
                )
            )

        # In Quiet Mode, suppress VOICE and BROWSER_NOTIFICATION
        if quiet_mode_enabled:
            return actions

        # 2. Check if this exact intervention_id was already delivered to voice/notification
        is_repeat_delivery = intervention.intervention_id in self._dispatched_interventions

        # Escalation check: MODERATE -> HIGH bypasses cooldown once
        prev_level = self._last_category_level.get(category, RiskLevel.LOW)
        is_escalation = (prev_level == RiskLevel.MODERATE and level == RiskLevel.HIGH)

        # 3. VOICE Channel evaluation
        if voice_alerts_enabled and (level in (RiskLevel.MODERATE, RiskLevel.HIGH)):
            if not is_repeat_delivery:
                voice_cooldown = self.policy.get_voice_cooldown(category)
                last_voice = self._last_voice_time.get(category, 0.0)
                time_since_voice = current_mono - last_voice

                if is_escalation or (time_since_voice >= voice_cooldown):
                    actions.append(
                        AlertAction(
                            alert_id=f"alert-voice-{uuid.uuid4().hex[:8]}",
                            intervention_id=intervention.intervention_id,
                            category=category,
                            risk_level=level,
                            channel=AlertChannel.VOICE,
                            message=msg,
                            priority=priority,
                            requires_acknowledgement=requires_ack,
                        )
                    )
                    self._last_voice_time[category] = current_mono

        # 4. BROWSER_NOTIFICATION Channel evaluation
        if browser_notifications_enabled and (level in (RiskLevel.MODERATE, RiskLevel.HIGH)):
            if not is_repeat_delivery:
                last_notif = self._last_notification_time.get(category, 0.0)
                time_since_notif = current_mono - last_notif

                if is_escalation or (time_since_notif >= self.policy.notification_cooldown_sec):
                    actions.append(
                        AlertAction(
                            alert_id=f"alert-notif-{uuid.uuid4().hex[:8]}",
                            intervention_id=intervention.intervention_id,
                            category=category,
                            risk_level=level,
                            channel=AlertChannel.BROWSER_NOTIFICATION,
                            message=msg,
                            priority=priority,
                            requires_acknowledgement=requires_ack,
                        )
                    )
                    self._last_notification_time[category] = current_mono

        # Update tracking state
        self._dispatched_interventions.add(intervention.intervention_id)
        self._last_category_level[category] = level

        return actions


# Global singleton orchestrator
alert_orchestrator = AlertOrchestrator()
