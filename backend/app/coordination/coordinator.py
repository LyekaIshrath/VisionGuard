"""VisionGuard Monitoring Coordinator.

Authoritative state machine orchestrating all monitoring subsystems:
- Camera Hardware
- MediaPipe Perception Pipeline
- Built-in / Personalized Ergonomic Baselines
- Workstation Activity Collector (Zero Keylogging)
- Work Activity Classification Engine
- Temporal Risk & Intervention Engines
- Session Aggregator & Event Timeline

Lifecycle States:
STOPPED -> STARTING -> MONITORING -> STOPPING -> COMPLETED
"""

from __future__ import annotations

import uuid
import time
import logging
import threading
from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from app.camera.manager import get_camera_manager, CameraManager
from app.perception.engine import get_perception_engine, PerceptionEngine
from app.activity.collector import get_activity_collector, WorkstationActivityCollector
from app.activity.engine import get_work_activity_engine, WorkActivityEngine, WorkActivityState
from app.intelligence.baselines import get_effective_posture_baseline, get_effective_alertness_baseline
from app.sessions.service import session_service
from app.human_state.models import HumanState

logger = logging.getLogger(__name__)


class CoordinatorState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    MONITORING = "MONITORING"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"


class MonitoringCoordinator:
    """Coordinates atomic startup, runtime fusion, and teardown for a single session."""

    def __init__(self):
        self._state: CoordinatorState = CoordinatorState.STOPPED
        self._lock = threading.Lock()

        # Authoritative Session Identity
        self._session_id: Optional[str] = None
        self._user_id: Optional[str] = None
        self._started_at: Optional[datetime] = None
        self._ended_at: Optional[datetime] = None

        # Timeline Event Storage
        self._timeline_events: List[Dict[str, Any]] = []
        self._preview_fps: float = 0.0
        self._last_presence: Optional[bool] = None
        self._last_activity_state: Optional[str] = None
        self._last_posture_risk: Optional[str] = None
        self._last_alertness_risk: Optional[str] = None

        # Activity Interval Tracking
        self._current_interval_state: str = "UNKNOWN"
        self._interval_start_time: Optional[datetime] = None
        self._interval_start_mono: Optional[float] = None
        self._interval_reasons: List[str] = []

        # Subsystems
        self._camera_manager: CameraManager = get_camera_manager()
        self._perception: PerceptionEngine = get_perception_engine()
        self._activity_collector: WorkstationActivityCollector = get_activity_collector()
        self._activity_engine: WorkActivityEngine = get_work_activity_engine()

        # Hook frame callback
        self._camera_manager.on_frame(self._on_frame_received)

    @property
    def state(self) -> CoordinatorState:
        with self._lock:
            return self._state

    @property
    def session_id(self) -> Optional[str]:
        with self._lock:
            return self._session_id

    @property
    def timeline_events(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._timeline_events)

    @property
    def preview_fps(self) -> float:
        return getattr(self, "_preview_fps", 0.0)

    def get_timeline(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._timeline_events)

    def record_event(self, event_type: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Record an immutable, timestamped event to the timeline."""
        event = {
            "event_id": str(uuid.uuid4()),
            "session_id": self._session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "metadata": metadata or {},
        }
        with self._lock:
            self._timeline_events.append(event)

    def start_monitoring(self, user_id: Optional[str] = None, token: Optional[str] = None) -> Dict[str, Any]:
        """Atomically start all local monitoring subsystems under ONE session_id.

        Rolls back cleanly on local hardware/subsystem failure.
        """
        with self._lock:
            if self._state in (CoordinatorState.STARTING, CoordinatorState.MONITORING):
                return {
                    "success": True,
                    "status": self._state.value,
                    "session_id": self._session_id,
                    "message": "Monitoring is already active.",
                }

            self._state = CoordinatorState.STARTING
            self._session_id = str(uuid.uuid4())
            self._user_id = user_id
            self._started_at = datetime.now(timezone.utc)
            self._timeline_events.clear()
            self._last_presence = None
            self._last_activity_state = None
            self._last_posture_risk = None
            self._last_alertness_risk = None
            self._current_interval_state = "UNKNOWN"
            self._interval_start_time = datetime.now(timezone.utc)
            self._interval_start_mono = time.monotonic()
            self._interval_reasons = []

        # Step 1: Baseline Selection
        p_base, p_src, p_conf = get_effective_posture_baseline(
            self._perception._calibration_service.baseline
            if self._perception._calibration_service.is_calibrated
            else None
        )
        a_base, a_src, a_conf = get_effective_alertness_baseline(
            self._perception._alertness_calibration_service.baseline
            if self._perception._alertness_calibration_service.is_calibrated
            else None
        )

        # Step 2: Start Camera
        try:
            cam_result = self._camera_manager.start()
            if cam_result == "CAMERA_ERROR":
                self._rollback("camera", "CAMERA_START_FAILED", "Webcam hardware could not be initialized.")
                return {
                    "success": False,
                    "failed_component": "camera",
                    "error_code": "CAMERA_START_FAILED",
                    "message": "Webcam hardware could not be initialized.",
                }
        except Exception as e:
            self._rollback("camera", "CAMERA_EXCEPTION", str(e))
            return {
                "success": False,
                "failed_component": "camera",
                "error_code": "CAMERA_EXCEPTION",
                "message": f"Camera start error: {e}",
            }

        # Step 3: Start Perception Pipeline
        try:
            self._perception.reset_session()
            self._perception.start_worker(self._camera_manager)
        except Exception as e:
            self._rollback("perception", "PERCEPTION_START_FAILED", str(e))
            return {
                "success": False,
                "failed_component": "perception",
                "error_code": "PERCEPTION_START_FAILED",
                "message": f"Perception engine worker failed: {e}",
            }

        # Step 4: Start Workstation Activity Collector
        try:
            self._activity_collector.reset()
            self._activity_collector.start()
        except Exception as e:
            self._rollback("activity_collector", "COLLECTOR_START_FAILED", str(e))
            return {
                "success": False,
                "failed_component": "activity_collector",
                "error_code": "COLLECTOR_START_FAILED",
                "message": f"Activity collector failed to start: {e}",
            }

        # Step 5: Reset Activity Engine
        self._activity_engine.reset()

        # Step 6: Reset Posture / Alertness / Risk
        self._perception._posture_analyzer.reset_state()
        self._perception._alertness_analyzer.reset_state()
        self._perception._risk_engine.reset()

        # Step 7: Initialize Session Aggregator
        try:
            session_service.start_session(user_id=user_id, token=token, session_id=self._session_id)
        except Exception as e:
            logger.warning(f"Cloud session registration notice: {e} (local session continuing)")

        # Step 8: Record SESSION_START
        self.record_event("SESSION_START", {
            "session_id": self._session_id,
            "started_at": self._started_at.isoformat(),
            "baseline_source": "PERSONALIZED" if (p_src == "PERSONALIZED" or a_src == "PERSONALIZED") else "BUILT_IN",
        })

        with self._lock:
            self._state = CoordinatorState.MONITORING

        return {
            "success": True,
            "status": "MONITORING",
            "session_id": self._session_id,
            "started_at": self._started_at.isoformat(),
            "baseline_source": "PERSONALIZED" if (p_src == "PERSONALIZED" or a_src == "PERSONALIZED") else "BUILT_IN",
        }

    def _rollback(self, failed_component: str, error_code: str, message: str) -> None:
        """Cleanly rollback all started subsystems on hardware/initialization failure."""
        logger.error(f"Rolling back monitoring startup due to {failed_component} failure: {error_code} - {message}")
        try:
            self._perception.stop_worker()
        except Exception:
            pass
        try:
            self._activity_collector.stop()
        except Exception:
            pass
        try:
            self._camera_manager.stop()
        except Exception:
            pass
        with self._lock:
            self._state = CoordinatorState.STOPPED
            self._session_id = None

    def _record_and_transition_interval(self, new_state: str, reasons: List[str]) -> None:
        """Close previous interval, persist to MongoDB, and start new interval."""
        if not self._session_id or self._interval_start_mono is None or self._interval_start_time is None:
            self._current_interval_state = new_state
            self._interval_start_time = datetime.now(timezone.utc)
            self._interval_start_mono = time.monotonic()
            self._interval_reasons = list(reasons)
            return

        now = datetime.now(timezone.utc)
        now_mono = time.monotonic()
        duration_sec = max(0.05, round(now_mono - self._interval_start_mono, 2))

        try:
            from app.db.mongodb import mongo_repository
            mongo_repository.activity_intervals.record_interval(
                user_id=self._user_id or "anonymous",
                session_id=self._session_id,
                state=self._current_interval_state,
                start_time=self._interval_start_time,
                end_time=now,
                duration_seconds=duration_sec,
                signals_summary={"reasons": list(self._interval_reasons)},
            )
        except Exception as e:
            logger.warning(f"Error persisting activity interval: {e}")

        self._current_interval_state = new_state
        self._interval_start_time = now
        self._interval_start_mono = now_mono
        self._interval_reasons = list(reasons)

    def _finalize_active_interval(self) -> None:
        """Finalize and persist the active interval on session stop."""
        if not self._session_id or self._interval_start_mono is None or self._interval_start_time is None:
            return

        now = datetime.now(timezone.utc)
        now_mono = time.monotonic()
        duration_sec = max(0.05, round(now_mono - self._interval_start_mono, 2))

        try:
            from app.db.mongodb import mongo_repository
            mongo_repository.activity_intervals.record_interval(
                user_id=self._user_id or "anonymous",
                session_id=self._session_id,
                state=self._current_interval_state,
                start_time=self._interval_start_time,
                end_time=now,
                duration_seconds=duration_sec,
                signals_summary={"reasons": list(self._interval_reasons), "final": True},
            )
        except Exception as e:
            logger.warning(f"Error finalizing activity interval: {e}")

        self._interval_start_time = None
        self._interval_start_mono = None

    def stop_monitoring(self) -> Dict[str, Any]:
        """Atomically stop all subsystems, finalize intervals, and generate session report."""
        with self._lock:
            if self._state == CoordinatorState.STOPPED:
                return {
                    "status": "STOPPED",
                    "session_id": None,
                    "session_summary": None,
                }
            self._state = CoordinatorState.STOPPING
            self._ended_at = datetime.now(timezone.utc)

        # 1. Stop Activity Collection
        self._activity_collector.stop()
        activity_snapshot = self._activity_collector.get_snapshot()

        # 2. Finalize and persist final activity interval
        self._finalize_active_interval()

        # 3. Record SESSION_STOP event
        self.record_event("SESSION_STOP", {
            "ended_at": self._ended_at.isoformat(),
            "keyboard_events": activity_snapshot.keyboard_event_count,
            "mouse_movements": activity_snapshot.mouse_movement_count,
            "mouse_clicks": activity_snapshot.mouse_click_count,
        })

        # 4. Transfer final workstation snapshot telemetry into aggregator
        if session_service.aggregator:
            session_service.aggregator.keyboard_event_count = max(
                session_service.aggregator.keyboard_event_count,
                activity_snapshot.keyboard_event_count
            )
            session_service.aggregator.mouse_event_count = max(
                session_service.aggregator.mouse_event_count,
                activity_snapshot.mouse_movement_count
            )
            session_service.aggregator.mouse_click_count = max(
                session_service.aggregator.mouse_click_count,
                activity_snapshot.mouse_click_count
            )
            session_service.aggregator.scroll_count = max(
                session_service.aggregator.scroll_count,
                activity_snapshot.scroll_count
            )
            session_service.aggregator.longest_idle_seconds = max(
                session_service.aggregator.longest_idle_seconds,
                activity_snapshot.idle_seconds
            )
            session_service.aggregator.timeline = list(self._timeline_events)

        # 5. Finalize Aggregation & Persist to MongoDB
        session_summary = session_service.stop_session()
        if session_summary:
            session_summary["timeline"] = list(self._timeline_events)

        # 4. Stop Perception & Release Camera
        self._perception.stop_session()
        self._perception.stop_worker()
        self._camera_manager.stop()

        # 5. Cancel pending voice alerts
        try:
            self._perception._intervention_engine.reset()
        except Exception:
            pass

        with self._lock:
            self._state = CoordinatorState.COMPLETED
            final_id = self._session_id

        return {
            "status": "COMPLETED",
            "session_id": final_id,
            "session_summary": session_summary,
            "timeline_events_count": len(self._timeline_events),
            "timeline_events": list(self._timeline_events),
        }

    def _on_frame_received(self, frame_bytes: Optional[bytes]) -> None:
        """Observe processed frames and drive work activity + event timeline."""
        if self._state != CoordinatorState.MONITORING:
            return

        state = self._perception.get_latest_state()
        if state is None:
            return

        activity_snap = self._activity_collector.get_snapshot()
        decision = self._activity_engine.evaluate(state, activity_snap)

        # Inject activity decision into HumanState
        state.activity_state = decision.state.value
        state.activity_score = decision.score
        state.activity_confidence = decision.confidence
        state.activity_reason_codes = decision.reason_codes
        state.idle_seconds = activity_snap.idle_seconds
        state.keyboard_activity_count = activity_snap.keyboard_event_count
        state.mouse_activity_count = activity_snap.mouse_movement_count + activity_snap.mouse_click_count
        state.screen_activity_level = activity_snap.screen_activity_level
        state.screen_change_score = activity_snap.screen_change_score

        # Event Timeline Generation on Transitions
        # 1. Presence transitions
        person_now = state.person_detected
        if self._last_presence is None:
            self._last_presence = person_now
            if person_now:
                self.record_event("PERSON_DETECTED")
        elif self._last_presence != person_now:
            if person_now:
                self.record_event("PERSON_RETURNED")
            else:
                self.record_event("PERSON_LEFT")
            self._last_presence = person_now

        # 2. Activity state transitions and interval persistence
        act_now = decision.state.value
        if self._last_activity_state != act_now:
            self.record_event(f"STATE_{act_now}", {"reasons": decision.reason_codes, "score": decision.score})
            self._last_activity_state = act_now
            self._record_and_transition_interval(act_now, decision.reason_codes)

        # Feed enriched state (including activity, computer, and screen signals) to session aggregator
        if self._session_id:
            state.mouse_click_count = activity_snap.mouse_click_count
            state.scroll_count = activity_snap.scroll_count
            session_service.on_frame_processed(state)

        # 3. Prolonged eye closure event
        if state.eye_closure_duration and state.eye_closure_duration >= 2.0:
            self.record_event("LONG_EYE_CLOSURE", {"duration_sec": state.eye_closure_duration})

        # 4. Posture / Alertness risk transitions
        risk_state = self._perception.risk_engine.latest_state
        if risk_state and risk_state.posture_risk:
            post_lvl = risk_state.posture_risk.level.value
            if post_lvl in ("MODERATE", "HIGH") and self._last_posture_risk not in ("MODERATE", "HIGH"):
                self.record_event("POSTURE_RISK_START", {"level": post_lvl})
            elif post_lvl == "LOW" and self._last_posture_risk in ("MODERATE", "HIGH"):
                self.record_event("POSTURE_RISK_RESOLVED")
            self._last_posture_risk = post_lvl

        if risk_state and risk_state.alertness_risk:
            alt_lvl = risk_state.alertness_risk.level.value
            if alt_lvl in ("MODERATE", "HIGH") and self._last_alertness_risk not in ("MODERATE", "HIGH"):
                self.record_event("ALERTNESS_RISK_START", {"level": alt_lvl})
            elif alt_lvl == "LOW" and self._last_alertness_risk in ("MODERATE", "HIGH"):
                self.record_event("ALERTNESS_RISK_RESOLVED")
            self._last_alertness_risk = alt_lvl


# Singleton coordinator instance
_monitoring_coordinator: Optional[MonitoringCoordinator] = None
_coord_lock = threading.Lock()


def get_monitoring_coordinator() -> MonitoringCoordinator:
    """Get or create singleton MonitoringCoordinator."""
    global _monitoring_coordinator
    with _coord_lock:
        if _monitoring_coordinator is None:
            _monitoring_coordinator = MonitoringCoordinator()
        return _monitoring_coordinator
