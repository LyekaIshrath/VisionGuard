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
from app.sessions.repository import SupabaseSessionRepository

logger = logging.getLogger("visionguard.sessions")


class SessionService:
    """
    Coordinates local session metrics aggregation and downstream cloud persistence.
    Real-time perception and risk loops NEVER wait on cloud calls.
    """
    def __init__(self, repository: Optional[SupabaseSessionRepository] = None):
        self.repository = repository or SupabaseSessionRepository()
        self.local_session_id: Optional[str] = None
        self.cloud_session_id: Optional[str] = None
        self.current_user_id: Optional[str] = None
        self.current_token: Optional[str] = None
        self.aggregator: Optional[SessionAggregator] = None
        self.cloud_status: str = "DISABLED" if not config.is_cloud_configured() else "SYNCED"
        self.last_error: Optional[str] = None

    def get_cloud_status(self) -> CloudStatusResponse:
        configured = config.is_cloud_configured()
        if not configured:
            status = "DISABLED"
            message = "Supabase cloud persistence is not configured. Running locally only."
        else:
            status = self.cloud_status
            if status == "SYNCED":
                message = "Monitoring sessions and risk events synchronized with cloud."
            elif status == "SYNCING":
                message = "Synchronization operation in progress."
            elif status == "OFFLINE":
                message = "Cloud unavailable. VisionGuard operating in local-only fallback mode."
            elif status == "ERROR":
                message = f"Cloud operation failed: {self.last_error or 'Unknown error'}"
            else:
                message = f"Status: {status}"

        return CloudStatusResponse(
            status=status,
            configured=configured,
            cloud_session_id=self.cloud_session_id,
            local_session_id=self.local_session_id,
            message=message
        )

    def start_session(self, user_id: Optional[str] = None, token: Optional[str] = None) -> str:
        """
        Starts a new local monitoring session and schedules cloud creation if authenticated.
        Guarantees NO split-brain: local monitoring is authoritative.
        """
        self.local_session_id = str(uuid.uuid4())
        self.current_user_id = user_id
        self.current_token = token
        self.cloud_session_id = None
        self.last_error = None

        self.aggregator = SessionAggregator(
            session_id=self.local_session_id,
            user_id=user_id or "local_user"
        )

        if config.is_cloud_configured() and user_id and token:
            self.cloud_status = "SYNCING"
            # Asynchronously create cloud session so camera start is instantaneous
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._async_start_cloud_session(self.local_session_id, user_id, token))
            except RuntimeError:
                pass
        else:
            self.cloud_status = "DISABLED" if not config.is_cloud_configured() else "OFFLINE"

        logger.info(f"Local session started: {self.local_session_id} (Cloud status: {self.cloud_status})")
        return self.local_session_id

    async def start_session_async(self, user_id: Optional[str] = None, token: Optional[str] = None) -> str:
        """Starts a session and awaits cloud session creation."""
        self.local_session_id = str(uuid.uuid4())
        self.current_user_id = user_id
        self.current_token = token
        self.cloud_session_id = None
        self.last_error = None

        self.aggregator = SessionAggregator(
            session_id=self.local_session_id,
            user_id=user_id or "local_user"
        )

        if config.is_cloud_configured() and user_id and token:
            self.cloud_status = "SYNCING"
            await self._async_start_cloud_session(self.local_session_id, user_id, token)
        else:
            self.cloud_status = "DISABLED" if not config.is_cloud_configured() else "OFFLINE"

        return self.local_session_id

    async def _async_start_cloud_session(self, session_id: str, user_id: str, token: str) -> None:
        try:
            # 1. Clean up any previous stale ACTIVE sessions for this user
            try:
                interrupted_count = await self.repository.mark_stale_sessions_interrupted(
                    user_id=user_id,
                    token=token,
                    current_session_id=session_id
                )
                if interrupted_count > 0:
                    logger.info(f"Marked {interrupted_count} stale sessions as INTERRUPTED.")
            except Exception as e:
                logger.warning(f"Could not check stale sessions: {e}")

            # 2. Create the cloud session record
            started_at = datetime.now(timezone.utc).isoformat()
            payload = {
                "id": session_id,
                "user_id": user_id,
                "started_at": started_at,
                "status": "ACTIVE",
                "device_name": "VisionGuard Desktop"
            }
            res = await self.repository.create_session(token=token, payload=payload)
            if res:
                self.cloud_session_id = session_id
                self.cloud_status = "SYNCED"
                logger.info(f"Cloud session created: {self.cloud_session_id}")
            else:
                self.cloud_session_id = None
                self.cloud_status = "ERROR"
                self.last_error = "Cloud returned empty session representation"
        except Exception as e:
            self.cloud_session_id = None
            self.cloud_status = "OFFLINE"
            self.last_error = str(e)
            logger.warning(f"Cloud session creation failed (local monitoring continues): {e}")

    def on_frame_processed(self, state: HumanState, mono_time: Optional[float] = None) -> None:
        """Ingests a HumanState into the aggregator (100% in-memory, zero network wait)."""
        if self.aggregator:
            self.aggregator.add_sample(state, mono_time)

    def record_risk_event(self, event: Any) -> None:
        """Records a risk event in memory and queues idempotent persistence to Supabase."""
        if self.aggregator:
            self.aggregator.record_risk_event()

        if self.current_token and self.current_user_id and config.is_cloud_configured():
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._async_persist_risk_event(event, self.current_user_id, self.current_token))
            except RuntimeError:
                pass

    async def record_risk_event_async(self, event: Any) -> None:
        """Records a risk event and awaits persistence to Supabase."""
        if self.aggregator:
            self.aggregator.record_risk_event()

        if self.current_token and self.current_user_id and config.is_cloud_configured():
            await self._async_persist_risk_event(event, self.current_user_id, self.current_token)

    async def _async_persist_risk_event(self, event: Any, user_id: str, token: str) -> None:
        try:
            raw_ts = getattr(event, "timestamp", None)
            if isinstance(raw_ts, str):
                dt_utc = datetime.fromisoformat(raw_ts)
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
                "session_id": self.cloud_session_id or self.local_session_id,
                "user_id": user_id,
                "timestamp": dt_utc.isoformat(),
                "category": cat_val,
                "severity": sev_val,
                "reason": reason_val,
                "lifecycle": lifecycle_val,
                "duration_seconds": duration_val,
                "metadata": {
                    "source": "visionguard_risk_engine"
                }
            }
            await self.repository.upsert_risk_event(token=token, payload=payload)
        except Exception as e:
            logger.warning(f"Failed to persist risk event: {e}")

    def record_intervention(self, intervention: Intervention) -> None:
        if self.aggregator:
            self.aggregator.record_intervention()

    def stop_session(self) -> Dict[str, Any]:
        """Finalizes the session, computes time-weighted summaries, and queues cloud update."""
        if not self.aggregator:
            return {"status": "NO_ACTIVE_SESSION"}

        summary = self.aggregator.get_summary()
        summary["session_id"] = self.local_session_id
        summary["ended_at"] = datetime.now(timezone.utc).isoformat()
        summary["status"] = "COMPLETED"

        if self.current_token and (self.cloud_session_id or self.local_session_id) and config.is_cloud_configured():
            target_id = self.cloud_session_id or self.local_session_id
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._async_stop_cloud_session(target_id, self.current_token, summary))
            except RuntimeError:
                pass

        # Reset local state
        self.aggregator = None
        self.local_session_id = None
        self.cloud_session_id = None
        return summary

    async def stop_session_async(self) -> Dict[str, Any]:
        """Finalizes the session and awaits cloud persistence."""
        if not self.aggregator:
            return {"status": "NO_ACTIVE_SESSION"}

        summary = self.aggregator.get_summary()
        summary["session_id"] = self.local_session_id
        summary["ended_at"] = datetime.now(timezone.utc).isoformat()
        summary["status"] = "COMPLETED"

        if self.current_token and (self.cloud_session_id or self.local_session_id) and config.is_cloud_configured():
            target_id = self.cloud_session_id or self.local_session_id
            await self._async_stop_cloud_session(target_id, self.current_token, summary)

        self.aggregator = None
        self.local_session_id = None
        self.cloud_session_id = None
        return summary

    async def _async_stop_cloud_session(self, session_id: str, token: str, summary: Dict[str, Any]) -> None:
        try:
            self.cloud_status = "SYNCING"
            payload = {
                "ended_at": summary["ended_at"],
                "duration_seconds": summary["duration_seconds"],
                "good_posture_seconds": summary["good_posture_seconds"],
                "posture_risk_seconds": summary["posture_risk_seconds"],
                "alertness_risk_seconds": summary["alertness_risk_seconds"],
                "average_posture_score": summary["average_posture_score"],
                "average_alertness_score": summary["average_alertness_score"],
                "risk_event_count": summary["risk_event_count"],
                "intervention_count": summary["intervention_count"],
                "status": "COMPLETED"
            }
            await self.repository.update_session(session_id=session_id, token=token, payload=payload)
            self.cloud_status = "SYNCED"
            logger.info(f"Cloud session {session_id} finalized successfully.")
        except Exception as e:
            self.cloud_status = "ERROR"
            self.last_error = str(e)
            logger.warning(f"Failed to finalize cloud session {session_id}: {e}")


# Global singleton
session_service = SessionService()
