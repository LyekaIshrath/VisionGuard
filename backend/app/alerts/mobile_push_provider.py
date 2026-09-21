"""VisionGuard Mobile Push Notification Provider.

Delivers real push notifications to registered mobile devices and PWAs using
the standard W3C Web Push Protocol (VAPID / RFC 8291 / RFC 8292).

Strict Privacy Guarantees:
- Payload NEVER contains camera frames, screenshots, or facial/pose landmarks.
- Payload NEVER contains keystroke content or mouse coordinates.
- Transmits ONLY high-level derived events (title, message, event_type, severity, timestamp, session_id).
"""

from __future__ import annotations

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pywebpush import webpush, WebPushException
from py_vapid import Vapid
from cryptography.hazmat.primitives import serialization
import base64

from app.alerts.models import MobilePushPayload
from app.db.mongodb import mongo_repository

logger = logging.getLogger("visionguard.push")


class MobilePushProvider:
    """Delivers push alerts to registered user devices with strict user isolation."""

    def __init__(
        self,
        claims_sub: Optional[str] = None,
    ):
        self._claims_sub = claims_sub or os.getenv("VAPID_CLAIMS_SUB", "mailto:alerts@visionguard.local")
        self._vapid: Optional[Vapid] = None
        self._public_key: Optional[str] = None
        self._key_file = os.path.join(os.path.dirname(__file__), "..", "..", ".vapid_private.pem")
        self._ensure_vapid_keys()

    def _ensure_vapid_keys(self) -> None:
        """Load or generate persistent VAPID keypair in .vapid_private.pem."""
        try:
            if os.path.exists(self._key_file):
                self._vapid = Vapid.from_file(self._key_file)
            else:
                self._vapid = Vapid()
                self._vapid.generate_keys()
                self._vapid.save_key(self._key_file)
        except Exception as e:
            logger.warning(f"Failed to load VAPID key file, generating ephemeral: {e}")
            self._vapid = Vapid()
            self._vapid.generate_keys()

        raw_pub = self._vapid.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        self._public_key = base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode("ascii")

    @property
    def public_key(self) -> str:
        """Derive standard uncompressed URL-safe base64 public key for PushManager."""
        return self._public_key or ""

    def send_push_to_user(
        self,
        user_id: str,
        payload: MobilePushPayload,
    ) -> Dict[str, Any]:
        """Deliver a push notification to all enabled mobile devices owned strictly by user_id."""
        devices = mongo_repository.notification_devices.get_user_devices(
            user_id=user_id,
            enabled_only=True,
            sanitize=False,
        )

        if not devices:
            return {
                "user_id": user_id,
                "targeted_devices": 0,
                "delivered": 0,
                "failed": 0,
                "message": "No active registered devices found for user.",
            }

        # Privacy Whitelist Validation: Enforce ONLY derived telemetry fields
        safe_payload = {
            "event_type": payload.event_type,
            "severity": payload.severity,
            "title": payload.title,
            "message": payload.message,
            "timestamp": payload.timestamp,
            "session_id": payload.session_id,
        }
        payload_data = json.dumps(safe_payload)

        delivered = 0
        failed = 0

        for device in devices:
            sub = device.get("push_subscription")
            device_id = device.get("device_id")
            if not sub or not isinstance(sub, dict) or not sub.get("endpoint"):
                continue

            try:
                webpush(
                    subscription_info=sub,
                    data=payload_data,
                    vapid_private_key=self._vapid,
                    vapid_claims={"sub": self._claims_sub},
                    timeout=5.0,
                )
                delivered += 1
                if device_id:
                    mongo_repository.notification_devices.update_last_seen(user_id, device_id)
            except WebPushException as ex:
                failed += 1
                status = getattr(ex.response, "status_code", None) if hasattr(ex, "response") else None
                logger.warning(f"WebPush delivery failed for device {device_id} (HTTP {status}): {ex}")
                # Auto-unregister inactive/expired subscriptions (HTTP 404 Not Found or 410 Gone)
                if status in (404, 410) and device_id:
                    logger.info(f"Unregistering expired subscription device: {device_id}")
                    mongo_repository.notification_devices.unregister_device(user_id, device_id)
            except Exception as e:
                failed += 1
                logger.warning(f"Unexpected push delivery error: {e}")

        return {
            "user_id": user_id,
            "targeted_devices": len(devices),
            "delivered": delivered,
            "failed": failed,
        }

    def send_test_push(self, user_id: str) -> Dict[str, Any]:
        """Send an immediate test alert to verify physical mobile delivery."""
        test_payload = MobilePushPayload(
            event_type="TEST_ALERT",
            severity="LOW",
            title="VisionGuard Test Alert",
            message="Your mobile device is connected and receiving real-time posture & alertness notifications.",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        return self.send_push_to_user(user_id=user_id, payload=test_payload)


mobile_push_provider = MobilePushProvider()
