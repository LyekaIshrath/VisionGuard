"""VisionGuard Session Service.

Coordinates local session aggregation and authoritative MongoDB persistence.
Real-time perception and risk loops NEVER wait on database calls.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from app.config import config
from app.human_state.models import HumanState
from app.alerts.models import RiskEvent, Intervention
from app.sessions.models import CloudStatusResponse
from app.sessions.aggregator import SessionAggregator
from app.sessions.repository import MongoSessionRepository
from app.db.mongodb import MongoDBClient, SessionRepository, ActivityEventRepository

logger = logging.getLogger("visionguard.sessions")


class SessionService:
    """Coordinates local session metrics aggregation and MongoDB persistence."""

    def __init__(self, repository: Optional[MongoSessionRepository] = None):
        self.mongo_client = MongoDBClient.get_instance()
        self.repository = repository or MongoSessionRepository(self.mongo_client)
        self.mongo_session_repo = SessionRepository(self.mongo_client)
        self.mongo_event_repo = ActivityEventRepository(self.mongo_client)
        self.local_session_id: Optional[str] = None
        self.cloud_session_id: Optional[str] = None
        self.current_user_id: Optional[str] = None
        self.current_token: Optional[str] = None
        self.aggregator: Optional[SessionAggregator] = None
        self.cloud_status: str = "SYNCED" if self.mongo_client.is_connected else "OFFLINE"
        self.mongo_status: str = "SYNCED" if self.mongo_client.is_connected else "OFFLINE"
        self.last_error: Optional[str] = None

    def get_cloud_status(self) -> CloudStatusResponse:
        configured = config.is_cloud_configured()
        if not configured:
            status = "DISABLED"
            message = "Persistence unconfigured. Running locally only."
        else:
            connected = self.mongo_client.is_connected
            status = "SYNCED" if connected else "OFFLINE"
            message = (
                "MongoDB application persistence active and synchronized."
                if connected
                else "MongoDB unreachable. Operating in local fallback mode."
            )
        return CloudStatusResponse(
            status=status,
            configured=configured,
            cloud_session_id=self.cloud_session_id,
            local_session_id=self.local_session_id,
            message=message,
        )

    def start_session(
        self,
        user_id: Optional[str] = None,
        token: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Starts a new local monitoring session and persists session start to MongoDB."""
        self.local_session_id = session_id or str(uuid.uuid4())
        self.current_user_id = user_id
        self.current_token = token
        self.cloud_session_id = self.local_session_id if user_id else None
        self.last_error = None

        self.aggregator = SessionAggregator(
            session_id=self.local_session_id,
            user_id=user_id or "local_user",
        )

        effective_user_id = user_id or "local_user"
        self.current_user_id = effective_user_id
        if not config.is_cloud_configured():
            self.cloud_session_id = None
            self.cloud_status = "DISABLED"
            return self.local_session_id

        # Persist session start to MongoDB for authenticated user
        try:
            self.mongo_session_repo.mark_stale_sessions_interrupted(
                user_id=effective_user_id,
                current_session_id=self.local_session_id,
            )
            self.mongo_session_repo.create_session(
                user_id=effective_user_id,
                session_id=self.local_session_id,
                started_at=datetime.now(timezone.utc),
            )
            self.cloud_status = "SYNCED"
        except Exception as e:
            logger.warning(f"MongoDB session start error: {e}")
            self.cloud_session_id = None
            self.cloud_status = "OFFLINE"
            self.last_error = str(e)

        logger.info(f"Local session started: {self.local_session_id} (Mongo status: {self.cloud_status})")
        return self.local_session_id

    async def _async_start_cloud_session(self, session_id: str, user_id: str, token: str) -> None:
        """Compatibility helper for resilience testing and async session creation."""
        try:
            await self.repository.mark_stale_sessions_interrupted(
                user_id=user_id,
                token=token,
                current_session_id=session_id,
            )
            res = await self.repository.create_session(
                user_id=user_id,
                session_id=session_id,
                started_at=datetime.now(timezone.utc),
            )
            if res:
                self.cloud_session_id = session_id
                self.cloud_status = "SYNCED"
            else:
                self.cloud_session_id = None
                self.cloud_status = "ERROR"
        except Exception as e:
            self.cloud_session_id = None
            self.cloud_status = "OFFLINE"
            self.last_error = str(e)

    async def start_session_async(
        self,
        user_id: Optional[str] = None,
        token: Optional[str] = None,
    ) -> str:
        local_id = self.start_session(user_id=user_id, token=token)
        if user_id and token and config.is_cloud_configured():
            await self._async_start_cloud_session(local_id, user_id, token)
        return local_id

    def on_frame_processed(self, state: HumanState, mono_time: Optional[float] = None) -> None:
        if self.aggregator:
            self.aggregator.add_sample(state, mono_time)

    def record_risk_event(self, event: Any) -> None:
        if self.aggregator:
            self.aggregator.record_risk_event()

        if self.current_user_id and self.local_session_id:
            try:
                raw_ts = getattr(event, "timestamp", None)
                if isinstance(raw_ts, str):
                    dt_utc = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                elif isinstance(raw_ts, datetime):
                    dt_utc = raw_ts
                else:
                    dt_utc = datetime.now(timezone.utc)

                event_id = getattr(event, "id", getattr(event, "event_id", str(uuid.uuid4())))
                cat_obj = getattr(event, "category", "SYSTEM")
                cat_val = cat_obj.value if hasattr(cat_obj, "value") else str(cat_obj)

                sev_obj = getattr(event, "severity", getattr(event, "risk_level", getattr(event, "level", "UNKNOWN")))
                sev_val = sev_obj.value if hasattr(sev_obj, "value") else str(sev_obj)

                lifecycle_obj = getattr(event, "lifecycle", getattr(event, "status", "STARTED"))
                lifecycle_val = lifecycle_obj.value if hasattr(lifecycle_obj, "value") else str(lifecycle_obj)

                reason_val = getattr(event, "reason", getattr(event, "message", "Risk event"))
                duration_val = getattr(event, "duration_seconds", getattr(event, "duration_sec", 0.0))

                payload = {
                    "id": event_id,
                    "session_id": self.local_session_id,
                    "user_id": self.current_user_id,
                    "timestamp": dt_utc,
                    "category": cat_val,
                    "severity": sev_val,
                    "reason": reason_val,
                    "lifecycle": lifecycle_val,
                    "duration_seconds": duration_val,
                    "metadata": {"source": "visionguard_risk_engine"},
                }
                self.repository.risk_events.record_risk_event(
                    user_id=self.current_user_id,
                    session_id=self.local_session_id,
                    event_data=payload,
                )
            except Exception as e:
                logger.warning(f"Failed to persist risk event to MongoDB: {e}")

    async def record_risk_event_async(self, event: Any) -> None:
        self.record_risk_event(event)

    def record_intervention(self, intervention: Intervention) -> None:
        if self.aggregator:
            self.aggregator.record_intervention()

    def stop_session(self) -> Dict[str, Any]:
        if not self.aggregator:
            return {"status": "NO_ACTIVE_SESSION"}

        summary = self.aggregator.get_summary()
        duration = summary.get("duration_seconds", 0.0)
        ended_at = datetime.now(timezone.utc)

        summary["session_id"] = self.local_session_id
        summary["ended_at"] = ended_at.isoformat()
        summary["status"] = "COMPLETED"

        effective_user_id = self.current_user_id or "local_user"
        if self.local_session_id:
            try:
                saved = self.mongo_session_repo.finalize_session(
                    user_id=effective_user_id,
                    session_id=self.local_session_id,
                    ended_at=ended_at,
                    duration_seconds=duration,
                    report_data=summary,
                )
                self.mongo_status = "SAVED" if saved else "OFFLINE"
                self.cloud_status = "SYNCED" if saved else "OFFLINE"
            except Exception as me:
                logger.warning(f"MongoDB session finalization error: {me}")
                self.mongo_status = "OFFLINE"
                self.cloud_status = "OFFLINE"

        self.aggregator = None
        self.local_session_id = None
        self.cloud_session_id = None
        return summary

    async def stop_session_async(self) -> Dict[str, Any]:
        return self.stop_session()


session_service = SessionService()
