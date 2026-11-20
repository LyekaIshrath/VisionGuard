"""VisionGuard Alert Orchestrator.

Strictly downstream coordination of alert actions across delivery surfaces:
1. IN-APP ALERT (InterventionBanner)
2. DESKTOP / WINDOWS BROWSER NOTIFICATION (Native Web Notification API)
3. VOICE ALERTS (Synthesized voice audio)
4. MOBILE PUSH NOTIFICATIONS (Web Push)

Enforces anti-spam, independent cooldowns, escalation rules, acknowledgement,
and granular user event preferences (posture, alertness, extended away, session complete).
NEVER accesses camera frames or runs MediaPipe inference.
"""

from __future__ import annotations

import time
import uuid
import logging
from typing import Dict, List, Optional, Set, Any
from datetime import datetime, timezone

from app.intelligence.risk_models import RiskCategory, RiskLevel
from app.alerts.models import (
    Intervention,
    AlertAction,
    AlertChannel,
    AlertPriority,
    EventStatus,
    RiskEvent,
    MobilePushPayload,
)
from app.alerts.policy import AlertPolicyConfig, DEFAULT_ALERT_POLICY
from app.alerts.mobile_push_provider import mobile_push_provider

logger = logging.getLogger("visionguard.alerts")


class AlertOrchestrator:
    """Downstream decision engine determining delivery eligibility across all channels."""

    def __init__(self, policy: Optional[AlertPolicyConfig] = None):
        self.policy = policy or DEFAULT_ALERT_POLICY

        # Monotonic timestamp of last dispatched alert per channel and category
        self._last_voice_time: Dict[RiskCategory, float] = {}
        self._last_notification_time: Dict[RiskCategory, float] = {}
        self._last_mobile_push_time: Dict[RiskCategory, float] = {}

        # Cooldowns
        self.mobile_cooldown_sec = 60.0

        # Set of acknowledged intervention IDs
        self._acknowledged_interventions: Set[str] = set()

        # Set of intervention IDs dispatched to prevent repeat deliveries
        self._dispatched_interventions: Set[str] = set()

        # Active interventions per category
        self._active_interventions: Dict[RiskCategory, Intervention] = {}

        # Last evaluated risk level per category
        self._last_category_level: Dict[RiskCategory, RiskLevel] = {}

    def evaluate_intervention(
        self,
        intervention: Intervention,
        voice_alerts_enabled: bool = False,
        browser_notifications_enabled: bool = False,
        mobile_push_enabled: bool = False,
        quiet_mode_enabled: bool = False,
        notify_posture: bool = True,
        notify_alertness: bool = True,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        current_mono: Optional[float] = None,
    ) -> List[AlertAction]:
        """Evaluates an incoming Intervention against the policy and user preferences.
        Returns a list of AlertAction directives for the client.
        """
        if current_mono is None:
            current_mono = time.monotonic()

        category = intervention.category
        level = intervention.level

        # UNKNOWN or LOW produce NO audible/browser/push alerts
        if level in (RiskLevel.UNKNOWN, RiskLevel.LOW):
            self.handle_resolution(category)
            return []

        # Check granular event filters
        if category == RiskCategory.POSTURE and not notify_posture:
            return []
        if category == RiskCategory.ALERTNESS and not notify_alertness:
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

        # In Quiet Mode, suppress VOICE, BROWSER_NOTIFICATION, and MOBILE_PUSH
        if quiet_mode_enabled:
            return actions

        is_repeat_delivery = intervention.intervention_id in self._dispatched_interventions
        prev_level = self._last_category_level.get(category, RiskLevel.LOW)
        is_escalation = (prev_level == RiskLevel.MODERATE and level == RiskLevel.HIGH)

        # 2. VOICE Channel evaluation
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

        # 3. BROWSER_NOTIFICATION Channel evaluation (Desktop Windows/Browser Toast)
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

        # 4. Mobile Push Channel evaluation (Backward compatibility)
        if mobile_push_enabled and (level in (RiskLevel.MODERATE, RiskLevel.HIGH)):
            last_push = self._last_mobile_push_time.get(category, 0.0)
            time_since_push = current_mono - last_push
            if is_escalation or (time_since_push >= self.mobile_cooldown_sec):
                actions.append(
                    AlertAction(
                        alert_id=f"alert-mobile-{uuid.uuid4().hex[:8]}",
                        intervention_id=intervention.intervention_id,
                        category=category,
                        risk_level=level,
                        channel=AlertChannel.MOBILE_PUSH,
                        message=msg,
                        priority=priority,
                        requires_acknowledgement=requires_ack,
                    )
                )
                self._last_mobile_push_time[category] = current_mono

        # Update tracking state
        self._dispatched_interventions.add(intervention.intervention_id)
        self._last_category_level[category] = level

        return actions

    def acknowledge_alert(self, intervention_id: str) -> bool:
        """User explicit acknowledgement of high-priority alert."""
        self._acknowledged_interventions.add(intervention_id)
        return True

    def is_acknowledged(self, intervention_id: str) -> bool:
        """Check if an intervention has already been acknowledged by user."""
        return intervention_id in self._acknowledged_interventions

    def handle_resolution(self, category: RiskCategory) -> None:
        """Reset escalation and active tracking upon risk resolution."""
        self._active_interventions[category] = None
        self._last_category_level[category] = RiskLevel.LOW

    def reset_session(self) -> None:
        """Reset session-scoped tracking states on session stop/start."""
        self._acknowledged_interventions.clear()
        self._dispatched_interventions.clear()
        self._active_interventions.clear()
        self._last_voice_time.clear()
        self._last_notification_time.clear()
        self._last_mobile_push_time.clear()
        self._last_category_level.clear()

    def dispatch_lifecycle_event(
        self,
        event_type: str,
        user_id: str,
        title: str,
        message: str,
        session_id: Optional[str] = None,
        preferences: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Dispatch lifecycle events (e.g. MONITORING_STOPPED, SESSION_REPORT_READY, PROLONGED_AWAY)."""
        return {"delivered": 0, "message": "Lifecycle event processed"}


# Global singleton orchestrator
alert_orchestrator = AlertOrchestrator()
