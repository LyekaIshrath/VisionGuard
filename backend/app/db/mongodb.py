"""VisionGuard MongoDB Database and Repository Layer.

Strict Invariants:
- MongoDB handles VisionGuard application persistence and user accounts.
- Zero Supabase runtime dependencies.
- All repository methods enforce authenticated user ownership via user_id.
- Explicit idempotent ensure_indexes() called on initialization.
- Truthful offline fallback: if MongoDB is unreachable, operations return safe
  offline status without crashing local perception or monitoring.
"""

from __future__ import annotations

import os
import time
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import pymongo
from pymongo import MongoClient, IndexModel, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

logger = logging.getLogger("visionguard.mongodb")

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "visionguard")


def _resolve_user_id(user_id: Optional[str] = None, token: Optional[str] = None) -> Optional[str]:
    """Helper to derive user_id from explicit arg or verified token."""
    if user_id:
        return user_id
    if token:
        try:
            from app.auth.service import decode_access_token
            payload = decode_access_token(token)
            return payload.get("sub")
        except Exception:
            return None
    return None


class MongoDBClient:
    """Manages thread-safe MongoDB connection pool and collection access."""

    _instance: Optional[MongoDBClient] = None

    def __init__(self, uri: str = MONGODB_URI, db_name: str = MONGODB_DATABASE):
        self.uri = uri
        self.db_name = db_name
        self._client: Optional[MongoClient] = None
        self._db = None
        self._is_connected = False

    @classmethod
    def get_instance(cls) -> MongoDBClient:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def connect(self) -> bool:
        """Connect to MongoDB and run ensure_indexes() if successful."""
        try:
            self._client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=2000,
                connectTimeoutMS=2000,
                maxPoolSize=50,
            )
            self._client.admin.command("ping")
            self._db = self._client[self.db_name]
            self._is_connected = True
            self.ensure_indexes()
            logger.info(f"Connected to MongoDB at {self.uri} (Database: {self.db_name})")
            return True
        except Exception as e:
            logger.warning(f"MongoDB connection notice: {e} (operating in DATA SYNC OFFLINE mode)")
            self._is_connected = False
            self._db = None
            return False

    @property
    def is_connected(self) -> bool:
        if not self._is_connected or self._client is None:
            return False
        try:
            self._client.admin.command("ping")
            return True
        except Exception:
            self._is_connected = False
            return False

    @property
    def db(self):
        if not self.is_connected and self._client is None:
            self.connect()
        return self._db

    def ensure_indexes(self) -> bool:
        """Create explicit idempotent indexes across all collections."""
        if self._db is None:
            return False

        try:
            # 1. users
            self._db.users.create_indexes([
                IndexModel([("email", ASCENDING)], unique=True, name="uniq_user_email"),
                IndexModel([("created_at", DESCENDING)], name="idx_user_created"),
            ])

            # 2. monitoring_sessions
            self._db.monitoring_sessions.create_indexes([
                IndexModel([("session_id", ASCENDING)], unique=True, name="uniq_session_id"),
                IndexModel([("user_id", ASCENDING), ("started_at", DESCENDING)], name="idx_user_started"),
                IndexModel([("user_id", ASCENDING), ("status", ASCENDING)], name="idx_user_status"),
            ])

            # 3. activity_intervals
            self._db.activity_intervals.create_indexes([
                IndexModel([("session_id", ASCENDING), ("start_time", ASCENDING)], name="idx_session_start_time"),
                IndexModel([("user_id", ASCENDING), ("start_time", ASCENDING)], name="idx_user_start_time"),
                IndexModel([("session_id", ASCENDING), ("started_at", ASCENDING)], name="idx_session_started"),
            ])

            # 4. activity_events
            self._db.activity_events.create_indexes([
                IndexModel([("event_id", ASCENDING)], unique=True, name="uniq_event_id"),
                IndexModel([("session_id", ASCENDING), ("timestamp", ASCENDING)], name="idx_session_time"),
                IndexModel([("user_id", ASCENDING), ("timestamp", ASCENDING)], name="idx_user_time"),
            ])

            # 5. risk_events
            self._db.risk_events.create_indexes([
                IndexModel([("event_id", ASCENDING)], unique=True, sparse=True, name="uniq_risk_event_id"),
                IndexModel([("session_id", ASCENDING), ("timestamp", ASCENDING)], name="idx_risk_session_time"),
                IndexModel([("user_id", ASCENDING), ("timestamp", ASCENDING)], name="idx_risk_user_time"),
            ])

            # 6. user_preferences & user_profiles
            self._db.user_preferences.create_indexes([
                IndexModel([("user_id", ASCENDING)], unique=True, name="uniq_user_prefs"),
            ])
            self._db.user_profiles.create_indexes([
                IndexModel([("user_id", ASCENDING)], unique=True, name="uniq_user_profile"),
            ])

            # 7. personal_goals
            self._db.personal_goals.create_indexes([
                IndexModel([("user_id", ASCENDING), ("goal_type", ASCENDING)], unique=True, name="uniq_user_goal_type"),
                IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_user_goals"),
            ])

            # 8. notification_devices
            self._db.notification_devices.create_indexes([
                IndexModel([("user_id", ASCENDING), ("push_subscription.endpoint", ASCENDING)], unique=True, sparse=True, name="uniq_user_device_endpoint"),
                IndexModel([("user_id", ASCENDING)], name="idx_user_devices"),
                IndexModel([("device_id", ASCENDING)], unique=True, sparse=True, name="uniq_device_id"),
            ])
            logger.info("MongoDB explicit indexes verified and created idempotently.")
            return True
        except Exception as e:
            logger.error(f"Failed to ensure MongoDB indexes: {e}")
            return False


# --- Repositories with Strict Authenticated User Ownership ---

class UserRepository:
    """Repository for user account persistence in MongoDB."""

    def __init__(self, db_client: Optional[MongoDBClient] = None):
        self._db_client = db_client or MongoDBClient.get_instance()
    def get_preferences(self, *args, **kwargs):
        return self.get_user_preferences(*args, **kwargs)


    def create_user(
        self,
        email: str,
        password_hash: str,
        display_name: Optional[str] = None,
        *args,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a new user with normalized email and password hash."""
        db = self._db_client.db
        if db is None:
            raise RuntimeError("Database connection unavailable.")

        norm_email = email.strip().lower()
        existing = db.users.find_one({"email": norm_email})
        if existing:
            raise ValueError(f"User with email '{norm_email}' already exists.")

        user_id = str(uuid.uuid4())
        name = display_name or norm_email.split("@")[0]
        now = datetime.now(timezone.utc)

        doc = {
            "_id": user_id,
            "id": user_id,
            "email": norm_email,
            "password_hash": password_hash,
            "display_name": name,
            "created_at": now,
            "updated_at": now,
            "status": "ACTIVE",
        }

        db.users.insert_one(doc)

        # Create default preferences
        db.user_preferences.update_one(
            {"user_id": user_id},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "browser_notifications_enabled": False,
                    "mobile_push_enabled": False,
                    "voice_alerts_enabled": True,
                    "voice_volume": 0.8,
                    "voice_rate": 1.0,
                    "voice_pitch": 1.0,
                    "quiet_mode_enabled": False,
                    "selected_voice": None,
                    "alert_language": "en",
                    "created_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )

        return {
            "id": user_id,
            "_id": user_id,
            "email": norm_email,
            "display_name": name,
            "created_at": now.isoformat(),
            "status": "ACTIVE",
        }

    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Retrieve user by normalized email (includes password_hash for authentication)."""
        db = self._db_client.db
        if db is None:
            return None
        norm_email = email.strip().lower()
        doc = db.users.find_one({"email": norm_email})
        if doc:
            doc["id"] = str(doc.get("_id", doc.get("id")))
        return doc


    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve user by ID (excludes password_hash)."""
        db = self._db_client.db
        if db is None:
            return None
        doc = db.users.find_one({"_id": str(user_id)}, {"password_hash": 0})
        if doc:
            doc["id"] = str(doc.get("_id", doc.get("id")))
            if isinstance(doc.get("created_at"), datetime):
                doc["created_at"] = doc["created_at"].isoformat()
            if isinstance(doc.get("updated_at"), datetime):
                doc["updated_at"] = doc["updated_at"].isoformat()
        return doc

    def delete_user(self, user_id: str) -> bool:
        """Permanently delete user record."""
        db = self._db_client.db
        if db is None:
            return False
        res = db.users.delete_one({"_id": str(user_id)})
        return res.deleted_count > 0


class SessionRepository:
    """Repository for monitoring_sessions with strict user_id isolation."""

    def __init__(self, db_client: Optional[MongoDBClient] = None):
        self._db_client = db_client or MongoDBClient.get_instance()
    def get_preferences(self, *args, **kwargs):
        return self.get_user_preferences(*args, **kwargs)


    def create_session(
        self,
        user_id: str,
        session_id: str,
        started_at: datetime,
        device_name: str = "VisionGuard Desktop",
    ) -> bool:
        """Create a new session record owned strictly by user_id."""
        db = self._db_client.db
        if db is None:
            return False

        doc = {
            "id": session_id,
            "session_id": session_id,
            "user_id": user_id,
            "started_at": started_at,
            "ended_at": None,
            "duration_seconds": 0.0,
            "good_posture_seconds": 0.0,
            "posture_risk_seconds": 0.0,
            "alertness_risk_seconds": 0.0,
            "average_posture_score": None,
            "average_alertness_score": None,
            "risk_event_count": 0,
            "intervention_count": 0,
            "valid_posture_seconds": 0.0,
            "valid_alertness_seconds": 0.0,
            "status": "RUNNING",
            "device_name": device_name,
            "presence_summary": {},
            "activity_summary": {},
            "computer_summary": {},
            "screen_summary": {},
            "eye_summary": {},
            "head_summary": {},
            "posture_summary": {},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        try:
            db.monitoring_sessions.update_one(
                {"session_id": session_id, "user_id": user_id},
                {"$set": doc},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error(f"Error creating session in MongoDB: {e}")
            return False

    def finalize_session(
        self,
        user_id: str,
        session_id: str,
        ended_at: datetime,
        duration_seconds: float,
        report_data: Dict[str, Any],
    ) -> bool:
        """Finalize and persist complete session report owned strictly by user_id."""
        from app.sessions.aggregator import validate_canonical_summary
        db = self._db_client.db
        if db is None:
            return False

        canonical = validate_canonical_summary(report_data)
        update_fields = {
            "ended_at": ended_at,
            "duration_seconds": round(duration_seconds, 1),
            "status": "COMPLETED",
            "good_posture_seconds": report_data.get("good_posture_seconds", 0.0),
            "posture_risk_seconds": report_data.get("posture_risk_seconds", 0.0),
            "alertness_risk_seconds": report_data.get("alertness_risk_seconds", 0.0),
            "average_posture_score": report_data.get("average_posture_score"),
            "average_alertness_score": report_data.get("average_alertness_score"),
            "risk_event_count": report_data.get("risk_event_count", 0),
            "intervention_count": report_data.get("intervention_count", 0),
            "valid_posture_seconds": report_data.get("valid_posture_seconds", 0.0),
            "valid_alertness_seconds": report_data.get("valid_alertness_seconds", 0.0),
            "presence_summary": canonical.presence_summary.model_dump(),
            "activity_summary": canonical.activity_summary.model_dump(),
            "computer_summary": canonical.computer_summary.model_dump(),
            "screen_summary": canonical.screen_summary.model_dump(),
            "eye_summary": canonical.eye_summary.model_dump(),
            "head_summary": canonical.head_summary.model_dump(),
            "posture_summary": canonical.posture_summary.model_dump(),
            "timeline": canonical.timeline,
            "updated_at": datetime.now(timezone.utc),
        }

        try:
            res = db.monitoring_sessions.update_one(
                {"session_id": session_id, "user_id": user_id},
                {"$set": update_fields},
            )
            return res.matched_count > 0
        except Exception as e:
            logger.error(f"Error finalizing session in MongoDB: {e}")
            return False

    def get_session(
        self,
        session_id: str,
        token: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a session strictly enforcing user ownership."""
        uid = _resolve_user_id(user_id, token)
        if not uid:
            return None

        db = self._db_client.db
        if db is None:
            return None

        try:
            doc = db.monitoring_sessions.find_one(
                {"session_id": session_id, "user_id": uid},
                {"_id": 0},
            )
            if doc:
                doc["id"] = doc.get("session_id", session_id)
                if isinstance(doc.get("started_at"), datetime):
                    doc["started_at"] = doc["started_at"].isoformat()
                if isinstance(doc.get("ended_at"), datetime):
                    doc["ended_at"] = doc["ended_at"].isoformat()
                if "activity_intervals" not in doc or not doc["activity_intervals"]:
                    intervals = list(db.activity_intervals.find(
                        {"session_id": session_id, "user_id": uid},
                        {"_id": 0}
                    ).sort("start_time", ASCENDING))
                    if intervals:
                        for itv in intervals:
                            if isinstance(itv.get("start_time"), datetime):
                                itv["start_time"] = itv["start_time"].isoformat()
                            if isinstance(itv.get("end_time"), datetime):
                                itv["end_time"] = itv["end_time"].isoformat()
                            if isinstance(itv.get("created_at"), datetime):
                                itv["created_at"] = itv["created_at"].isoformat()
                        doc["activity_intervals"] = intervals
            return doc

        except Exception as e:
            logger.error(f"Error reading session from MongoDB: {e}")
            return None

    def list_sessions(
        self,
        token: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List historical sessions strictly belonging to the authenticated user."""
        uid = _resolve_user_id(user_id, token)
        if not uid:
            return []

        db = self._db_client.db
        if db is None:
            return []

        try:
            cursor = (
                db.monitoring_sessions.find({"user_id": uid}, {"_id": 0})
                .sort("started_at", DESCENDING)
                .skip(offset)
                .limit(limit)
            )
            results = []
            for doc in cursor:
                doc["id"] = doc.get("session_id")
                if isinstance(doc.get("started_at"), datetime):
                    doc["started_at"] = doc["started_at"].isoformat()
                if isinstance(doc.get("ended_at"), datetime):
                    doc["ended_at"] = doc["ended_at"].isoformat()
                results.append(doc)
            return results
        except Exception as e:
            logger.error(f"Error listing sessions from MongoDB: {e}")
            return []

    def list_sessions_in_range(
        self,
        token: Optional[str] = None,
        user_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """List historical sessions in a time range strictly for user."""
        uid = _resolve_user_id(user_id, token)
        if not uid:
            return []

        db = self._db_client.db
        if db is None:
            return []

        query: Dict[str, Any] = {"user_id": uid}
        if start_time or end_time:
            time_filter: Dict[str, Any] = {}
            if start_time:
                try:
                    time_filter["$gte"] = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                except Exception:
                    time_filter["$gte"] = start_time
            if end_time:
                try:
                    time_filter["$lte"] = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                except Exception:
                    time_filter["$lte"] = end_time
            query["started_at"] = time_filter

        try:
            cursor = (
                db.monitoring_sessions.find(query, {"_id": 0})
                .sort("started_at", ASCENDING)
                .limit(limit)
            )
            results = []
            for doc in cursor:
                doc["id"] = doc.get("session_id")
                if isinstance(doc.get("started_at"), datetime):
                    doc["started_at"] = doc["started_at"].isoformat()
                if isinstance(doc.get("ended_at"), datetime):
                    doc["ended_at"] = doc["ended_at"].isoformat()
                results.append(doc)
            return results
        except Exception as e:
            logger.error(f"Error querying range sessions from MongoDB: {e}")
            return []

    def delete_session(
        self,
        session_id: str,
        token: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> bool:
        """Delete a session strictly belonging to user."""
        uid = _resolve_user_id(user_id, token)
        if not uid:
            return False

        db = self._db_client.db
        if db is None:
            return False

        try:
            res = db.monitoring_sessions.delete_one({"session_id": session_id, "user_id": uid})
            if res.deleted_count > 0:
                db.activity_events.delete_many({"session_id": session_id, "user_id": uid})
                db.activity_intervals.delete_many({"session_id": session_id, "user_id": uid})
                db.risk_events.delete_many({"session_id": session_id, "user_id": uid})
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting session from MongoDB: {e}")
            return False

    def mark_stale_sessions_interrupted(
        self,
        user_id: Optional[str] = None,
        token: Optional[str] = None,
        current_session_id: Optional[str] = None,
    ) -> int:
        """Finds active sessions for user (except current) and marks them INTERRUPTED."""
        uid = _resolve_user_id(user_id, token)
        if not uid:
            return 0

        db = self._db_client.db
        if db is None:
            return 0

        query: Dict[str, Any] = {"user_id": uid, "status": "ACTIVE"}
        if current_session_id:
            query["session_id"] = {"$ne": current_session_id}

        try:
            res = db.monitoring_sessions.update_many(
                query,
                {"$set": {"status": "INTERRUPTED", "updated_at": datetime.now(timezone.utc)}},
            )
            return res.modified_count
        except Exception as e:
            logger.error(f"Error marking stale sessions in MongoDB: {e}")
            return 0

    def cleanup_expired_sessions(
        self,
        user_id: Optional[str] = None,
        token: Optional[str] = None,
        retention_days: int = 30,
    ) -> int:
        """Deletes completed sessions older than retention_days for user."""
        uid = _resolve_user_id(user_id, token)
        if not uid or retention_days <= 0:
            return 0

        db = self._db_client.db
        if db is None:
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        try:
            # Find matching session_ids
            stale = list(
                db.monitoring_sessions.find(
                    {"user_id": uid, "status": "COMPLETED", "started_at": {"$lt": cutoff}},
                    {"session_id": 1},
                )
            )
            if not stale:
                return 0

            stale_ids = [s["session_id"] for s in stale if "session_id" in s]
            del_res = db.monitoring_sessions.delete_many(
                {"session_id": {"$in": stale_ids}, "user_id": uid}
            )
            db.activity_events.delete_many({"session_id": {"$in": stale_ids}, "user_id": uid})
            db.activity_intervals.delete_many({"session_id": {"$in": stale_ids}, "user_id": uid})
            db.risk_events.delete_many({"session_id": {"$in": stale_ids}, "user_id": uid})
            return del_res.deleted_count
        except Exception as e:
            logger.error(f"Error cleaning expired sessions in MongoDB: {e}")
            return 0


class ActivityEventRepository:
    """Repository for timeline activity_events with strict user_id isolation."""

    def __init__(self, db_client: Optional[MongoDBClient] = None):
        self._db_client = db_client or MongoDBClient.get_instance()
    def get_preferences(self, *args, **kwargs):
        return self.get_user_preferences(*args, **kwargs)


    def record_event(
        self,
        user_id: str,
        session_id: str,
        event_id: str,
        event_type: str,
        timestamp: datetime,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        db = self._db_client.db
        if db is None:
            return False

        doc = {
            "event_id": event_id,
            "session_id": session_id,
            "user_id": user_id,
            "event_type": event_type,
            "timestamp": timestamp,
            "metadata": metadata or {},
        }
        try:
            db.activity_events.update_one({"event_id": event_id}, {"$set": doc}, upsert=True)
            return True
        except Exception as e:
            logger.error(f"Error recording event in MongoDB: {e}")
            return False

    def list_events_for_session(
        self,
        arg1: str,
        arg2: Optional[str] = None,
        user_id: Optional[str] = None,
        token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # Supports both (session_id, user_id) and (user_id, session_id)
        db = self._db_client.db
        if db is None:
            return []

        if arg2 is not None:
            query = {
                "$or": [
                    {"session_id": arg1, "user_id": arg2},
                    {"session_id": arg2, "user_id": arg1},
                ]
            }
        else:
            uid = _resolve_user_id(user_id, token)
            query = {"session_id": arg1}
            if uid:
                query["user_id"] = uid

        try:
            cursor = db.activity_events.find(query, {"_id": 0}).sort("timestamp", ASCENDING)
            results = []
            for doc in cursor:
                if isinstance(doc.get("timestamp"), datetime):
                    doc["timestamp"] = doc["timestamp"].isoformat()
                results.append(doc)
            return results
        except Exception as e:
            logger.error(f"Error listing events from MongoDB: {e}")
            return []


class RiskEventRepository:
    """Repository for risk and intervention events with strict user_id isolation."""

    def __init__(self, db_client: Optional[MongoDBClient] = None):
        self._db_client = db_client or MongoDBClient.get_instance()
    def get_preferences(self, *args, **kwargs):
        return self.get_user_preferences(*args, **kwargs)


    def record_risk_event(
        self,
        user_id: str,
        session_id: str,
        event_data: Dict[str, Any],
    ) -> bool:
        db = self._db_client.db
        if db is None:
            return False

        event_id = event_data.get("id") or str(uuid.uuid4())
        ts = event_data.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.now(timezone.utc)
        elif not isinstance(ts, datetime):
            ts = datetime.now(timezone.utc)

        doc = {
            "id": event_id,
            "event_id": event_id,
            "session_id": session_id,
            "user_id": user_id,
            "timestamp": ts,
            "category": event_data.get("category", "SYSTEM"),
            "severity": event_data.get("severity", "LOW"),
            "reason": event_data.get("reason", ""),
            "lifecycle": event_data.get("lifecycle", "STARTED"),
            "duration_seconds": event_data.get("duration_seconds", 0.0),
            "metadata": event_data.get("metadata", {}),
        }
        try:
            db.risk_events.update_one({"id": event_id}, {"$set": doc}, upsert=True)
            return True
        except Exception as e:
            logger.error(f"Error recording risk event in MongoDB: {e}")
            return False

    def get_session_events(
        self,
        session_id: str,
        token: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        uid = _resolve_user_id(user_id, token)
        if not uid:
            return []

        db = self._db_client.db
        if db is None:
            return []

        try:
            cursor = (
                db.risk_events.find(
                    {"session_id": session_id, "user_id": uid},
                    {"_id": 0},
                ).sort("timestamp", ASCENDING)
            )
            results = []
            for doc in cursor:
                doc["id"] = doc.get("id") or doc.get("event_id")
                if isinstance(doc.get("timestamp"), datetime):
                    doc["timestamp"] = doc["timestamp"].isoformat()
                results.append(doc)
            return results
        except Exception as e:
            logger.error(f"Error getting session risk events: {e}")
            return []

    def list_events_in_range(
        self,
        token: Optional[str] = None,
        user_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        session_ids: Optional[List[str]] = None,
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        uid = _resolve_user_id(user_id, token)
        if not uid:
            return []

        db = self._db_client.db
        if db is None:
            return []

        query: Dict[str, Any] = {"user_id": uid}
        if session_ids is not None:
            if not session_ids:
                return []
            query["session_id"] = {"$in": session_ids}

        if start_time or end_time:
            time_filter: Dict[str, Any] = {}
            if start_time:
                try:
                    time_filter["$gte"] = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                except Exception:
                    time_filter["$gte"] = start_time
            if end_time:
                try:
                    time_filter["$lte"] = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                except Exception:
                    time_filter["$lte"] = end_time
            query["timestamp"] = time_filter

        try:
            cursor = db.risk_events.find(query, {"_id": 0}).sort("timestamp", ASCENDING).limit(limit)
            results = []
            for doc in cursor:
                doc["id"] = doc.get("id") or doc.get("event_id")
                if isinstance(doc.get("timestamp"), datetime):
                    doc["timestamp"] = doc["timestamp"].isoformat()
                results.append(doc)
            return results
        except Exception as e:
            logger.error(f"Error querying range risk events: {e}")
            return []


class UserPreferencesRepository:
    """Repository for user preferences and baselines with strict user_id isolation."""

    def __init__(self, db_client: Optional[MongoDBClient] = None):
        self._db_client = db_client or MongoDBClient.get_instance()
    def get_preferences(self, *args, **kwargs):
        return self.get_user_preferences(*args, **kwargs)


    def get_user_preferences(
        self,
        user_id: Optional[str] = None,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        uid = _resolve_user_id(user_id, token)
        defaults = {
            "user_id": uid or "",
            "browser_notifications_enabled": False,
            "voice_alerts_enabled": True,
            "voice_volume": 0.8,
            "voice_rate": 1.0,
            "voice_pitch": 1.0,
            "quiet_mode_enabled": False,
            "selected_voice": None,
            "alert_language": "en",
        }
        if not uid:
            return defaults

        db = self._db_client.db
        if db is None:
            return defaults

        try:
            doc = db.user_preferences.find_one({"user_id": uid}, {"_id": 0})
            if doc:
                defaults.update(doc)
            return defaults
        except Exception as e:
            logger.error(f"Error reading preferences from MongoDB: {e}")
            return defaults

    def update_user_preferences(self, user_id: Optional[str] = None, token: Optional[Any] = None, payload: Optional[Dict[str, Any]] = None, **kwargs):
        if payload is None and isinstance(token, dict):
            payload = token
            token = None
        return self.upsert_user_preferences(user_id=user_id, token=token, payload=payload)

    def upsert_user_preferences(
        self,
        user_id: Optional[str] = None,
        token: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        uid = _resolve_user_id(user_id, token)
        if not uid:
            return payload or {}

        db = self._db_client.db
        if db is None:
            return payload or {}

        clean = dict(payload or {})
        clean["user_id"] = uid
        clean["updated_at"] = datetime.now(timezone.utc)

        try:
            db.user_preferences.update_one(
                {"user_id": uid},
                {"$set": clean},
                upsert=True,
            )
            return self.get_user_preferences(user_id=uid)
        except Exception as e:
            logger.error(f"Error updating preferences in MongoDB: {e}")
            return clean


class PersonalGoalsRepository:
    """Repository for user personal wellness goals."""

    def __init__(self, db_client: Optional[MongoDBClient] = None):
        self._db_client = db_client or MongoDBClient.get_instance()
    def get_preferences(self, *args, **kwargs):
        return self.get_user_preferences(*args, **kwargs)


    def list_goals(
        self,
        user_id: Optional[str] = None,
        token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        uid = _resolve_user_id(user_id, token)
        if not uid:
            return []

        db = self._db_client.db
        if db is None:
            return []

        try:
            cursor = db.personal_goals.find({"user_id": uid}, {"_id": 0}).sort("created_at", ASCENDING)
            results = []
            for doc in cursor:
                doc["id"] = doc.get("id") or str(doc.get("goal_id", ""))
                if isinstance(doc.get("created_at"), datetime):
                    doc["created_at"] = doc["created_at"].isoformat()
                if isinstance(doc.get("updated_at"), datetime):
                    doc["updated_at"] = doc["updated_at"].isoformat()
                results.append(doc)
            return results
        except Exception as e:
            logger.error(f"Error listing goals: {e}")
            return []

    def upsert_goal(
        self,
        user_id: Optional[str] = None,
        token: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        uid = _resolve_user_id(user_id, token)
        if not uid or not payload:
            return None

        db = self._db_client.db
        if db is None:
            return None

        goal_type = payload.get("goal_type")
        target_val = payload.get("target_value")
        goal_id = payload.get("id") or str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        doc = {
            "id": goal_id,
            "user_id": uid,
            "goal_type": goal_type,
            "target_value": target_val,
            "updated_at": now,
        }
        try:
            db.personal_goals.update_one(
                {"user_id": uid, "goal_type": goal_type},
                {"$set": doc, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
            saved = db.personal_goals.find_one({"user_id": uid, "goal_type": goal_type}, {"_id": 0})
            if saved and isinstance(saved.get("created_at"), datetime):
                saved["created_at"] = saved["created_at"].isoformat()
            if saved and isinstance(saved.get("updated_at"), datetime):
                saved["updated_at"] = saved["updated_at"].isoformat()
            return saved
        except Exception as e:
            logger.error(f"Error upserting goal: {e}")
            return None

    def delete_goal(
        self,
        goal_id: str,
        user_id: Optional[str] = None,
        token: Optional[str] = None,
    ) -> bool:
        uid = _resolve_user_id(user_id, token)
        if not uid:
            return False

        db = self._db_client.db
        if db is None:
            return False

        try:
            res = db.personal_goals.delete_one({"id": goal_id, "user_id": uid})
            return res.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting goal: {e}")
            return False




class ActivityIntervalRepository:
    """Repository for state transition activity_intervals with strict user_id isolation."""

    def __init__(self, client: MongoDBClient):
        self._db_client = client

    def record_interval(
        self,
        user_id: str,
        session_id: str,
        state: str,
        start_time: datetime,
        end_time: datetime,
        duration_seconds: float,
        signals_summary: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Persist a closed work activity state interval."""
        db = self._db_client.db
        if db is None:
            return False

        doc = {
            "interval_id": str(uuid.uuid4()),
            "user_id": user_id,
            "session_id": session_id,
            "state": state,
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": round(duration_seconds, 2),
            "signals_summary": signals_summary or {},
            "created_at": datetime.now(timezone.utc),
        }

        try:
            db.activity_intervals.insert_one(doc)
            return True
        except Exception as e:
            logger.error(f"Error recording activity interval in MongoDB: {e}")
            return False

    def get_intervals(
        self,
        session_id: str,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """Retrieve all activity intervals for a session, ordered chronologically."""
        db = self._db_client.db
        if db is None:
            return []

        try:
            cursor = db.activity_intervals.find(
                {"session_id": session_id, "user_id": user_id},
                {"_id": 0}
            ).sort("start_time", ASCENDING)
            return list(cursor)
        except Exception as e:
            logger.error(f"Error reading activity intervals from MongoDB: {e}")
            return []

    def delete_intervals(self, session_id: str, user_id: str) -> int:
        """Delete all activity intervals for a session owned by user."""
        db = self._db_client.db
        if db is None:
            return 0
        try:
            res = db.activity_intervals.delete_many({"session_id": session_id, "user_id": user_id})
            return res.deleted_count
        except Exception as e:
            logger.error(f"Error deleting activity intervals: {e}")
            return 0


class NotificationDeviceRepository:
    """Repository for mobile push notification devices with strict user_id isolation."""

    def __init__(self, client: MongoDBClient):
        self._db_client = client

    def register_device(
        self,
        user_id: str,
        platform: str,
        device_name: str,
        push_subscription: Dict[str, Any],
        enabled: bool = True,
    ) -> Dict[str, Any]:
        """Register or update a user's mobile device for push notifications."""
        db = self._db_client.db
        if db is None:
            raise RuntimeError("Database disconnected")

        endpoint = push_subscription.get("endpoint", "")
        now = datetime.now(timezone.utc)
        device_id = str(uuid.uuid4())
        doc = {
            "user_id": user_id,
            "platform": platform,
            "device_name": device_name,
            "push_subscription": push_subscription,
            "enabled": enabled,
            "last_seen_at": now,
        }

        # Upsert by user_id and subscription endpoint
        from pymongo import ReturnDocument
        res = db.notification_devices.find_one_and_update(
            {"user_id": user_id, "push_subscription.endpoint": endpoint},
            {
                "$set": doc,
                "$setOnInsert": {"created_at": now, "device_id": device_id},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return {
            "device_id": res.get("device_id"),
            "platform": res.get("platform"),
            "device_name": res.get("device_name"),
            "enabled": res.get("enabled"),
            "last_seen_at": res.get("last_seen_at").isoformat() if hasattr(res.get("last_seen_at"), "isoformat") else str(res.get("last_seen_at")),
            "created_at": res.get("created_at").isoformat() if hasattr(res.get("created_at"), "isoformat") else str(res.get("created_at")),
        }

    def get_user_devices(
        self,
        user_id: str,
        enabled_only: bool = False,
        sanitize: bool = True,
    ) -> List[Dict[str, Any]]:
        """List registered devices for user. Never exposes subscription secrets when sanitized."""
        db = self._db_client.db
        if db is None:
            return []

        query = {"user_id": user_id}
        if enabled_only:
            query["enabled"] = True

        projection = {"_id": 0}
        if sanitize:
            projection["push_subscription.keys"] = 0

        cursor = db.notification_devices.find(query, projection).sort("last_seen_at", DESCENDING)
        devices = []
        for d in cursor:
            if "last_seen_at" in d and hasattr(d["last_seen_at"], "isoformat"):
                d["last_seen_at"] = d["last_seen_at"].isoformat()
            if "created_at" in d and hasattr(d["created_at"], "isoformat"):
                d["created_at"] = d["created_at"].isoformat()
            devices.append(d)
        return devices

    def unregister_device(self, user_id: str, device_id: str) -> bool:
        """Unregister a device owned strictly by user_id."""
        db = self._db_client.db
        if db is None:
            return False
        res = db.notification_devices.delete_one({"user_id": user_id, "device_id": device_id})
        return res.deleted_count > 0

    def update_last_seen(self, user_id: str, device_id: str) -> bool:
        db = self._db_client.db
        if db is None:
            return False
        res = db.notification_devices.update_one(
            {"user_id": user_id, "device_id": device_id},
            {"$set": {"last_seen_at": datetime.now(timezone.utc)}},
        )
        return res.matched_count > 0


class UnifiedMongoRepository:
    """Unified repository combining session, event, risk, preference, and goal operations.

    Drop-in replacement for the legacy SupabaseSessionRepository.
    Directly backed by MongoDB with strict user_id ownership enforcement.
    """

    def __init__(self, db_client: Optional[MongoDBClient] = None):
        self.client = db_client or MongoDBClient.get_instance()
        self.users = UserRepository(self.client)
        self.sessions = SessionRepository(self.client)
        self.activity_intervals = ActivityIntervalRepository(self.client)
        self.activity_events = ActivityEventRepository(self.client)
        self.notification_devices = NotificationDeviceRepository(self.client)
        self.risk_events = RiskEventRepository(self.client)
        self.preferences = UserPreferencesRepository(self.client)
        self.goals = PersonalGoalsRepository(self.client)

    # Session methods
    async def create_session(self, user_id: str, session_id: str, started_at: datetime, device_name: str = "VisionGuard Desktop"):
        return self.sessions.create_session(user_id, session_id, started_at, device_name)

    async def finalize_session(self, user_id: str, session_id: str, ended_at: datetime, duration_seconds: float, report_data: Dict[str, Any]):
        return self.sessions.finalize_session(user_id, session_id, ended_at, duration_seconds, report_data)

    async def get_session(self, session_id: str, token: Optional[str] = None, user_id: Optional[str] = None):
        return self.sessions.get_session(session_id, token, user_id)

    async def list_sessions(self, token: Optional[str] = None, user_id: Optional[str] = None, limit: int = 50, offset: int = 0):
        return self.sessions.list_sessions(token, user_id, limit, offset)

    async def list_sessions_in_range(self, token: Optional[str] = None, user_id: Optional[str] = None, start_time: Optional[str] = None, end_time: Optional[str] = None, limit: int = 1000):
        return self.sessions.list_sessions_in_range(token, user_id, start_time, end_time, limit)

    async def delete_session(self, session_id: str, token: Optional[str] = None, user_id: Optional[str] = None):
        return self.sessions.delete_session(session_id, token, user_id)

    async def mark_stale_sessions_interrupted(self, user_id: Optional[str] = None, token: Optional[str] = None, current_session_id: Optional[str] = None):
        return self.sessions.mark_stale_sessions_interrupted(user_id, token, current_session_id)

    async def cleanup_expired_sessions(self, user_id: Optional[str] = None, token: Optional[str] = None, retention_days: int = 30):
        return self.sessions.cleanup_expired_sessions(user_id, token, retention_days)

    # Risk event methods
    async def record_risk_event(self, user_id: str, session_id: str, event_data: Dict[str, Any]):
        return self.risk_events.record_risk_event(user_id, session_id, event_data)

    async def get_session_events(self, session_id: str, token: Optional[str] = None, user_id: Optional[str] = None):
        return self.risk_events.get_session_events(session_id, token, user_id)

    async def list_events_in_range(self, token: Optional[str] = None, user_id: Optional[str] = None, start_time: Optional[str] = None, end_time: Optional[str] = None, session_ids: Optional[List[str]] = None, limit: int = 5000):
        return self.risk_events.list_events_in_range(token, user_id, start_time, end_time, session_ids, limit)

    # Preference methods
    async def get_user_preferences(self, user_id: Optional[str] = None, token: Optional[str] = None):
        return self.preferences.get_user_preferences(user_id, token)

    async def upsert_user_preferences(self, user_id: Optional[str] = None, token: Optional[str] = None, payload: Optional[Dict[str, Any]] = None):
        return self.preferences.upsert_user_preferences(user_id, token, payload)

    # Goals methods
    async def list_goals(self, user_id: Optional[str] = None, token: Optional[str] = None):
        return self.goals.list_goals(user_id, token)

    async def upsert_goal(self, user_id: Optional[str] = None, token: Optional[str] = None, payload: Optional[Dict[str, Any]] = None):
        return self.goals.upsert_goal(user_id, token, payload)

    async def delete_goal(self, goal_id: str, token: Optional[str] = None, user_id: Optional[str] = None):
        return self.goals.delete_goal(goal_id, user_id, token)

    # User data deletion
    async def delete_user_data(self, user_id: Optional[str] = None, token: Optional[str] = None) -> Dict[str, Any]:
        uid = _resolve_user_id(user_id, token)
        if not uid:
            return {"status": "error", "message": "Unauthenticated user"}

        db = self.client.db
        if db is None:
            return {"status": "error", "message": "Database unavailable"}

        try:
            db.monitoring_sessions.delete_many({"user_id": uid})
            db.activity_events.delete_many({"user_id": uid})
            db.activity_intervals.delete_many({"user_id": uid})
            db.risk_events.delete_many({"user_id": uid})
            db.personal_goals.delete_many({"user_id": uid})
            db.user_preferences.delete_many({"user_id": uid})
            db.user_profiles.delete_many({"user_id": uid})

            return {
                "status": "success",
                "message": "All VisionGuard application data deleted successfully from MongoDB.",
                "deleted_user_id": uid,
            }
        except Exception as e:
            logger.error(f"Error deleting user data from MongoDB: {e}")
            return {"status": "error", "message": str(e)}


# Global singleton unified repository
mongo_repository = UnifiedMongoRepository()


