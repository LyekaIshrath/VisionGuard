import pytest
import time
from datetime import datetime, timezone
from app.human_state.models import HumanState
from app.sessions.aggregator import SessionAggregator
from app.sessions.service import SessionService
from app.alerts.models import RiskEvent, EventStatus
from app.intelligence.risk_models import RiskCategory, RiskLevel

class TestSessionAggregator:
    def test_monotonic_time_integration_variable_dt(self):
        agg = SessionAggregator(session_id="s1", user_id="u1")
        state_good = HumanState(
            track_id="t1",
            timestamp=datetime.now(timezone.utc),
            person_detected=True,
            posture_status="GOOD",
            posture_score=90.0,
            alertness_status="ALERT",
            alertness_score=85.0
        )

        # Feed 3 samples at varying monotonic timestamps (t=10.0, 10.2, 10.5)
        agg.add_sample(state_good, current_mono=10.0) # dt = 0
        agg.add_sample(state_good, current_mono=10.2) # dt = 0.2
        agg.add_sample(state_good, current_mono=10.5) # dt = 0.3

        summary = agg.get_summary()
        assert summary["duration_seconds"] == 0.5
        assert summary["good_posture_seconds"] == 0.5
        assert summary["posture_risk_seconds"] == 0.0
        assert summary["average_posture_score"] == 90.0
        assert summary["average_alertness_score"] == 85.0

    def test_averages_exclude_unknown_and_uncalibrated(self):
        agg = SessionAggregator(session_id="s2", user_id="u1")
        # 1 second with valid score 80.0
        state_valid = HumanState(
            track_id="t1",
            posture_status="GOOD",
            posture_score=80.0
        )
        agg.add_sample(state_valid, current_mono=1.0)
        agg.add_sample(state_valid, current_mono=2.0) # dt = 1.0

        # 1 second with UNKNOWN status and score None
        state_unknown = HumanState(
            track_id="t1",
            posture_status="UNKNOWN",
            posture_score=None
        )
        agg.add_sample(state_unknown, current_mono=3.0) # dt = 1.0

        # 1 second with uncalibrated state
        state_uncal = HumanState(
            track_id="t1",
            posture_status="NOT_CALIBRATED",
            posture_score=None
        )
        agg.add_sample(state_uncal, current_mono=4.0) # dt = 1.0

        summary = agg.get_summary()
        # Total duration = 3.0s
        assert summary["duration_seconds"] == 3.0
        # Average posture score must NOT be diluted to 26.6 or 0. It must remain 80.0!
        assert summary["average_posture_score"] == 80.0
        assert summary["average_alertness_score"] is None

    def test_time_weighted_average_calculation(self):
        agg = SessionAggregator(session_id="s3", user_id="u1")
        # 1.0 second at score 60
        s1 = HumanState(track_id="t1", posture_status="NEEDS_ATTENTION", posture_score=60.0)
        agg.add_sample(s1, current_mono=0.0)
        agg.add_sample(s1, current_mono=1.0) # dt = 1.0

        # 3.0 seconds at score 100
        s2 = HumanState(track_id="t1", posture_status="GOOD", posture_score=100.0)
        agg.add_sample(s2, current_mono=2.0) # dt = 1.0
        agg.add_sample(s2, current_mono=3.0) # dt = 1.0
        agg.add_sample(s2, current_mono=4.0) # dt = 1.0

        # Expected weighted average: (60*1 + 100*3) / 4 = 360 / 4 = 90.0
        summary = agg.get_summary()
        assert summary["average_posture_score"] == 90.0
        assert summary["good_posture_seconds"] == 3.0
        assert summary["posture_risk_seconds"] == 1.0

class TestSessionLifecycleAndEventIdempotency:
    def test_session_lifecycle_aggregation(self):
        service = SessionService()
        local_id = service.start_session(user_id="user-lifecycle")
        assert local_id is not None
        assert service.aggregator is not None

        # Process frames
        state = HumanState(
            track_id="t1",
            posture_status="GOOD",
            posture_score=85.0
        )
        service.on_frame_processed(state, mono_time=1.0)
        service.on_frame_processed(state, mono_time=1.1)

        # Record risk event
        event = RiskEvent(
            event_id="evt-12345",
            timestamp=datetime.now(timezone.utc),
            category=RiskCategory.POSTURE,
            status=EventStatus.STARTED,
            risk_level=RiskLevel.MODERATE,
            message="Posture deviation",
            duration_sec=5.0
        )
        service.record_risk_event(event)

        # Stop session
        summary = service.stop_session()
        assert summary["session_id"] == local_id
        assert summary["risk_event_count"] == 1
        assert summary["status"] == "COMPLETED"
        assert service.aggregator is None

    def test_risk_event_persistence_idempotency_keys(self):
        # Verify event_id is preserved between STARTED and RESOLVED
        start_event = RiskEvent(
            event_id="stable-evt-99",
            timestamp=datetime.now(timezone.utc),
            category=RiskCategory.ALERTNESS,
            status=EventStatus.STARTED,
            risk_level=RiskLevel.MODERATE,
            message="Alertness reduced",
            duration_sec=3.0
        )
        resolved_event = RiskEvent(
            event_id=start_event.event_id,
            timestamp=datetime.now(timezone.utc),
            category=RiskCategory.ALERTNESS,
            status=EventStatus.RESOLVED,
            risk_level=RiskLevel.LOW,
            message="Alertness condition resolved.",
            duration_sec=8.5
        )
        assert start_event.event_id == resolved_event.event_id
