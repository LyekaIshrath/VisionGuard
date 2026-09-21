"""VisionGuard Session and Cloud Repository Layer.

Pure MongoDB-backed persistence. Zero Supabase or PostgREST network calls.
Enforces authenticated user_id ownership on every database operation.
Strict field whitelists to ensure no raw frames, landmarks, or biometric vectors leak.
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.db.mongodb import (
    MongoDBClient,
    UnifiedMongoRepository,
    SessionRepository,
    ActivityEventRepository,
    RiskEventRepository,
    UserPreferencesRepository,
    PersonalGoalsRepository,
)

logger = logging.getLogger("visionguard.repository")

# Strict field whitelists to guarantee zero raw frames, landmarks, or biometric vectors leak
ALLOWED_SESSION_FIELDS = {
    "id", "session_id", "user_id", "started_at", "ended_at", "duration_seconds",
    "good_posture_seconds", "posture_risk_seconds", "alertness_risk_seconds",
    "average_posture_score", "average_alertness_score", "risk_event_count",
    "intervention_count", "valid_posture_seconds", "valid_alertness_seconds",
    "status", "device_name", "presence_summary", "activity_summary",
    "computer_summary", "screen_summary", "eye_summary", "head_summary",
    "posture_summary", "timeline", "created_at", "updated_at"
}

ALLOWED_RISK_EVENT_FIELDS = {
    "id", "event_id", "session_id", "user_id", "timestamp", "category",
    "severity", "reason", "lifecycle", "duration_seconds", "metadata"
}

ALLOWED_USER_PREFERENCE_FIELDS = {
    "user_id", "browser_notifications_enabled", "data_retention_days",
    "voice_alerts_enabled", "voice_volume", "voice_rate", "voice_pitch",
    "quiet_mode_enabled", "selected_voice", "timezone", "alert_language"
}

ALLOWED_PERSONAL_GOAL_FIELDS = {
    "id", "user_id", "goal_type", "target_value", "created_at", "updated_at"
}


class MongoSessionRepository(UnifiedMongoRepository):
    """Authoritative VisionGuard persistence repository backed by MongoDB."""

    def __init__(self, db_client: Optional[MongoDBClient] = None):
        super().__init__(db_client)

    @property
    def base_url(self) -> str:
        return ""

    @property
    def anon_key(self) -> str:
        return ""

    def filter_session_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if k in ALLOWED_SESSION_FIELDS}

    def filter_risk_event_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if k in ALLOWED_RISK_EVENT_FIELDS}

    def filter_preference_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if k in ALLOWED_USER_PREFERENCE_FIELDS}

    def filter_goal_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if k in ALLOWED_PERSONAL_GOAL_FIELDS}

    # Legacy method signature compatibility
    async def update_session(self, session_id: str, payload: Dict[str, Any], token: Optional[str] = None, user_id: Optional[str] = None) -> bool:
        from app.db.mongodb import _resolve_user_id
        uid = _resolve_user_id(user_id, token)
        db = self.client.db
        if db is None or not uid:
            return False
        clean = self.filter_session_payload(payload)
        try:
            res = db.monitoring_sessions.update_one(
                {"session_id": session_id, "user_id": uid},
                {"$set": clean}
            )
            return res.matched_count > 0
        except Exception as e:
            logger.error(f"Error updating session in MongoDB: {e}")
            return False

    async def upsert_risk_event(self, token: Optional[str] = None, user_id: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> bool:
        from app.db.mongodb import _resolve_user_id
        uid = _resolve_user_id(user_id, token)
        if not uid or not payload:
            return False
        clean = self.filter_risk_event_payload(payload)
        session_id = clean.get("session_id", "default")
        return await self.record_risk_event(user_id=uid, session_id=session_id, event_data=clean)


# SupabaseSessionRepository alias pointing to MongoSessionRepository for legacy test compatibility
SupabaseSessionRepository = MongoSessionRepository
