"""VisionGuard SMS Alert Notification Provider.

Coordinates safety alert dispatch to verified mobile numbers.
Enforces:
1. User phone verification check (phone_verified == True)
2. User preferences check (sms_alerts_enabled == True)
3. Granular event category filters (notify_posture, notify_alertness, notify_extended_away, notify_session_complete)
4. Independent SMS alert cooldown (120 seconds)
5. Strict privacy whitelist (text-only alerts, zero biometric or raw telemetry data)
"""

from __future__ import annotations

import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from app.notifications.sms_provider import sms_provider
from app.notifications.phone_utils import mask_phone_number
from app.db.mongodb import mongo_repository

logger = logging.getLogger("visionguard.alerts.sms")

# Strong deduplication and cooldown for SMS to avoid cellular spam / provider costs
DEFAULT_SMS_COOLDOWN_SECONDS = 120.0


class SmsNotificationProvider:
    """Downstream SMS alert provider invoked by AlertOrchestrator."""

    def __init__(self, cooldown_seconds: float = DEFAULT_SMS_COOLDOWN_SECONDS):
        self.cooldown_seconds = cooldown_seconds
        # user_id -> monotonic timestamp of last sent SMS
        self._last_sms_sent_at: Dict[str, float] = {}

    def send_alert_if_eligible(
        self,
        user_id: str,
        event_type: str,
        severity: str,
        title: str,
        message: str,
        current_mono: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Verify user verification state, preferences, cooldown, and dispatch SMS."""
        if not user_id or user_id in ("anonymous", "local_user"):
            return {"status": "SKIPPED", "reason": "UNAUTHENTICATED_SESSION"}

        now_mono = current_mono if current_mono is not None else time.monotonic()

        # 1. Fetch user account from MongoDB
        db = mongo_repository.client.db
        if db is None:
            return {"status": "SKIPPED", "reason": "DATABASE_UNAVAILABLE"}

        user_doc = db.users.find_one({"_id": str(user_id)})
        if not user_doc:
            return {"status": "SKIPPED", "reason": "USER_NOT_FOUND"}

        phone_number = user_doc.get("phone_number")
        phone_verified = bool(user_doc.get("phone_verified", False))

        if not phone_number or not phone_verified:
            logger.info(f"Skipping SMS for user {user_id}: phone number not verified.")
            return {"status": "SKIPPED", "reason": "PHONE_NOT_VERIFIED"}

        # 2. Fetch user preferences
        prefs = mongo_repository.preferences.get_user_preferences(user_id)
        if not prefs or not prefs.get("sms_alerts_enabled", True):
            logger.info(f"Skipping SMS for user {user_id}: SMS alerts disabled in preferences.")
            return {"status": "SKIPPED", "reason": "SMS_PREFERENCE_DISABLED"}

        # 3. Check granular category filters
        if "POSTURE" in event_type and not prefs.get("notify_posture", True):
            return {"status": "SKIPPED", "reason": "POSTURE_ALERTS_FILTERED"}
        if "ALERTNESS" in event_type and not prefs.get("notify_alertness", True):
            return {"status": "SKIPPED", "reason": "ALERTNESS_ALERTS_FILTERED"}
        if "AWAY" in event_type and not prefs.get("notify_extended_away", True):
            return {"status": "SKIPPED", "reason": "AWAY_ALERTS_FILTERED"}
        if "SESSION" in event_type and not prefs.get("notify_session_complete", True):
            return {"status": "SKIPPED", "reason": "SESSION_ALERTS_FILTERED"}

        # 4. Check cooldown
        last_sent = self._last_sms_sent_at.get(user_id, 0.0)
        elapsed = now_mono - last_sent
        if elapsed < self.cooldown_seconds:
            remaining = int(self.cooldown_seconds - elapsed)
            logger.info(f"Skipping SMS for user {user_id}: in cooldown ({remaining}s remaining).")
            return {"status": "SKIPPED", "reason": "COOLDOWN_ACTIVE", "remaining_seconds": remaining}

        # 5. Format privacy-safe SMS message
        local_time_str = datetime.now(timezone.utc).strftime("%I:%M %p UTC")
        sms_text = f"VisionGuard Alert: {title} - {message} detected at {local_time_str}. Open VisionGuard for details."

        try:
            dispatched = sms_provider.send_alert(phone_number, sms_text)
            if dispatched:
                self._last_sms_sent_at[user_id] = now_mono
                logger.info(f"SMS alert dispatched to {mask_phone_number(phone_number)} for {event_type}.")
                return {
                    "status": "DELIVERED",
                    "recipient": mask_phone_number(phone_number),
                    "event_type": event_type,
                }
            return {"status": "FAILED", "reason": "PROVIDER_FAILED"}
        except Exception as e:
            logger.warning(f"Failed to dispatch SMS alert to user {user_id}: {e}")
            return {"status": "FAILED", "error": str(e)}


sms_notification_provider = SmsNotificationProvider()
