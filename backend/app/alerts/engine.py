"""VisionGuard Mission 05: Intervention Engine.

Translates temporal risk states into structured, deduplicated events and
rate-limited, calm in-app/browser user interventions.
"""

from __future__ import annotations

import time
import uuid
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from app.intelligence.risk_config import RiskConfig, DEFAULT_RISK_CONFIG
from app.intelligence.risk_models import (
    RiskLevel,
    RiskCategory,
    RiskReasonCode,
    DomainRiskState,
    OverallRiskState,
)
from app.alerts.models import EventStatus, InterventionType, RiskEvent, Intervention


# Calm, non-medical intervention guidance
CALM_MESSAGES = {
    (RiskCategory.POSTURE, RiskLevel.MODERATE): (
        "Posture Adjustment",
        "Your posture has been away from your calibrated position for a while. Consider adjusting your sitting position.",
    ),
    (RiskCategory.POSTURE, RiskLevel.HIGH): (
        "Posture Strained",
        "Your posture has remained strained for an extended period. Consider sitting upright or taking a short movement break.",
    ),
    (RiskCategory.ALERTNESS, RiskLevel.MODERATE): (
        "Vigilance Check",
        "VisionGuard noticed sustained signs of reduced alertness. Consider taking a short break.",
    ),
    (RiskCategory.ALERTNESS, RiskLevel.HIGH): (
        "Rest Recommended",
        "VisionGuard is detecting persistent possible-drowsiness signals. Consider stopping focused work and resting before continuing.",
    ),
}


class InterventionEngine:
    """Thread-safe intervention engine with per-category cooldown and escalation."""

    def __init__(self, config: RiskConfig = DEFAULT_RISK_CONFIG) -> None:
        self._config = config
        self._lock = threading.Lock()

        # Bounded in-memory event history (STARTED and RESOLVED events)
        self._event_history: deque[RiskEvent] = deque(maxlen=self._config.max_event_history_size)

        # Active events per domain category (for ongoing state tracking and deduplication)
        self._active_events: Dict[RiskCategory, RiskEvent] = {}
        # Known active reason codes per category
        self._active_reasons: Dict[RiskCategory, Set[RiskReasonCode]] = {
            RiskCategory.POSTURE: set(),
            RiskCategory.ALERTNESS: set(),
        }

        # Rate-limiting / Cooldown tracking per category: monotonic timestamp of last alert
        self._last_alert_time: Dict[RiskCategory, float] = {}
        # Last alerted level per category (to enable MODERATE -> HIGH escalation bypass)
        self._last_alerted_level: Dict[RiskCategory, RiskLevel] = {}

        # Currently active intervention
        self._current_intervention: Optional[Intervention] = None
        self._on_event_callbacks: List[Any] = []

    def add_event_listener(self, callback: Any) -> None:
        self._on_event_callbacks.append(callback)

    def _notify_event_listeners(self, event: RiskEvent) -> None:
        for cb in self._on_event_callbacks:
            try:
                cb(event)
            except Exception:
                pass

    def reset_history(self) -> None:
        """Reset historical event ring buffer and cooldowns (REST POST /risk/events/reset).

        Note: Does NOT alter actual physical ongoing risk states.
        """
        with self._lock:
            self._event_history.clear()
            self._last_alert_time.clear()
            self._last_alerted_level.clear()
            self._current_intervention = None

    def reset_session(self) -> None:
        """Reset all state on monitoring start."""
        with self._lock:
            self._active_events.clear()
            self._active_reasons = {
                RiskCategory.POSTURE: set(),
                RiskCategory.ALERTNESS: set(),
            }
            self._last_alert_time.clear()
            self._last_alerted_level.clear()
            self._current_intervention = None

    def evaluate(
        self,
        risk_state: OverallRiskState,
        timestamp: Optional[float] = None,
    ) -> Optional[Intervention]:
        """Evaluate overall risk state, generate lifecycle events, and return intervention if qualified.

        Args:
            risk_state: Fused overall risk state from RiskEngine.
            timestamp: Monotonic seconds (optional, defaults to time.monotonic()).
        """
        now = timestamp if timestamp is not None else time.monotonic()

        with self._lock:
            # Evaluate domains independently (Posture and Alertness)
            posture_intervention = self._evaluate_domain(risk_state.posture_risk, now)
            alertness_intervention = self._evaluate_domain(risk_state.alertness_risk, now)

            # Prioritize Alertness intervention if both qualify simultaneously
            selected_intervention = alertness_intervention or posture_intervention
            if selected_intervention is not None:
                self._current_intervention = selected_intervention
            elif (
                risk_state.posture_risk.level == RiskLevel.LOW
                and risk_state.alertness_risk.level == RiskLevel.LOW
            ):
                # Both returned to low: clear active intervention
                self._current_intervention = None

            return self._current_intervention

    def _evaluate_domain(
        self,
        domain_state: DomainRiskState,
        now: float,
    ) -> Optional[Intervention]:
        """Process lifecycle transitions and cooldowns for an individual domain."""
        cat = domain_state.category
        level = domain_state.level
        reasons = set(domain_state.reasons)
        score = domain_state.score
        dur = domain_state.active_duration_sec

        active_event = self._active_events.get(cat)
        previous_reasons = self._active_reasons.get(cat, set())

        # 1. Check for Resolution (domain transitioned back to LOW)
        if level == RiskLevel.LOW:
            if active_event is not None:
                # Emit RESOLVED event
                resolved_event = RiskEvent(
                    event_id=active_event.event_id,
                    timestamp=datetime.now(timezone.utc),
                    category=cat,
                    status=EventStatus.RESOLVED,
                    risk_level=level,
                    risk_score=score,
                    message=f"{cat.value.title()} condition resolved.",
                    reason_codes=list(previous_reasons),
                    duration_sec=dur,
                )
                self._event_history.append(resolved_event)
                self._notify_event_listeners(resolved_event)
                del self._active_events[cat]
                self._active_reasons[cat] = set()
            return None

        # When domain is UNKNOWN: observation is paused, do NOT emit RESOLVED
        if level == RiskLevel.UNKNOWN:
            return None

        # 2. Check for Meaningful Transition or New Reason Codes
        is_level_escalation = False
        if active_event is None:
            is_level_escalation = True
        elif level == RiskLevel.HIGH and active_event.risk_level == RiskLevel.MODERATE:
            is_level_escalation = True

        new_reasons = reasons - previous_reasons
        is_new_reason = len(new_reasons) > 0

        # Generate event if level escalated or a new reason appeared
        if is_level_escalation or is_new_reason:
            title, default_msg = CALM_MESSAGES.get(
                (cat, level),
                (f"{cat.value.title()} Notice", f"{cat.value.title()} risk elevated to {level.value}."),
            )

            new_event = RiskEvent(
                event_id=str(uuid.uuid4())[:8],
                timestamp=datetime.now(timezone.utc),
                category=cat,
                status=EventStatus.STARTED,
                risk_level=level,
                risk_score=score,
                message=default_msg,
                reason_codes=list(reasons),
                duration_sec=dur,
            )
            self._event_history.append(new_event)
            self._notify_event_listeners(new_event)
            self._active_events[cat] = new_event
            self._active_reasons[cat] = reasons

        # 3. Check Cooldown and Escalation Policy for Interventions
        cooldown_sec = (
            self._config.cooldown_alertness_sec
            if cat == RiskCategory.ALERTNESS
            else self._config.cooldown_posture_sec
        )

        last_time = self._last_alert_time.get(cat, 0.0)
        last_lvl = self._last_alerted_level.get(cat, RiskLevel.LOW)
        elapsed_since_last = now - last_time

        # Escalation policy: MODERATE -> HIGH bypasses cooldown once
        bypass_cooldown = (level == RiskLevel.HIGH and last_lvl == RiskLevel.MODERATE)

        if (elapsed_since_last >= cooldown_sec) or bypass_cooldown:
            title, msg = CALM_MESSAGES.get(
                (cat, level),
                (f"{cat.value.title()} Notice", f"{cat.value.title()} risk elevated to {level.value}."),
            )
            intervention = Intervention(
                intervention_id=str(uuid.uuid4())[:8],
                timestamp=datetime.now(timezone.utc),
                category=cat,
                level=level,
                title=title,
                message=msg,
                type=InterventionType.IN_APP,
            )
            self._last_alert_time[cat] = now
            self._last_alerted_level[cat] = level
            return intervention

        return None

    @property
    def active_intervention(self) -> Optional[Intervention]:
        with self._lock:
            return self._current_intervention

    @property
    def event_history(self) -> List[RiskEvent]:
        with self._lock:
            return list(self._event_history)

    @property
    def active_events(self) -> List[RiskEvent]:
        with self._lock:
            return list(self._active_events.values())
