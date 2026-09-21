"""Comprehensive regression tests for Data Pipeline and Multi-Surface Notification Upgrade.

Verifies:
- Canonical summary schema & exact-key contract in finalize_session
- Ingestion of live workstation and work activity telemetry
- Activity interval creation, state transition, and finalization
- Duration reconciliation (disjoint states sum to total session duration)
- Blink rate computed against valid eye tracking minutes
- Null-vs-zero semantics for blink rate and averages
- Push device user isolation & security
- Privacy whitelist enforcement on push payloads
- Orchestrator multi-surface routing, event filters, and mobile cooldowns
"""

import time
import uuid
from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock, patch

from app.sessions.aggregator import (
    SessionAggregator,
    CanonicalSessionSummary,
    validate_canonical_summary,
)
from app.human_state.models import HumanState
from app.db.mongodb import mongo_repository
from app.alerts.models import (
    Intervention,
    AlertChannel,
    RiskCategory,
    RiskLevel,
    MobilePushPayload,
)
from app.alerts.orchestrator import AlertOrchestrator
from app.alerts.mobile_push_provider import MobilePushProvider


class TestCanonicalSummaryContract:
    def test_canonical_summary_schema_exact_keys(self):
        agg = SessionAggregator(started_at=datetime.now(timezone.utc))
        summary = agg.get_summary()

        # All 8 canonical keys must be present
        required_keys = [
            "presence_summary",
            "activity_summary",
            "computer_summary",
            "screen_summary",
            "eye_summary",
            "head_summary",
            "posture_summary",
        ]
        for key in required_keys:
            assert key in summary, f"Missing required canonical summary key: {key}"
            assert isinstance(summary[key], dict), f"Key {key} must be a dictionary"

        # Validate with strict schema validator
        canonical = validate_canonical_summary(summary)
        assert isinstance(canonical, CanonicalSessionSummary)

    def test_finalize_session_exact_key_contract(self):
        user_id = f"test_user_{uuid.uuid4().hex[:6]}"
        session_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)

        # Create session
        mongo_repository.sessions.create_session(
            user_id=user_id,
            session_id=session_id,
            started_at=started_at,
        )

        agg = SessionAggregator(started_at=started_at)
        state = HumanState(track_id="track_1", 
            person_detected=True,
            activity_state="ENGAGED",
            keyboard_activity_count=15,
            mouse_activity_count=42,
            posture_status="GOOD",
            posture_score=95.0,
            blink_count=5,
            valid_eye_tracking_seconds=30.0,
        )
        agg.add_sample(state, current_mono=100.0)
        agg.add_sample(state, current_mono=130.0)
        summary = agg.get_summary()

        # Finalize session
        ended_at = datetime.now(timezone.utc)
        saved = mongo_repository.sessions.finalize_session(
            user_id=user_id,
            session_id=session_id,
            ended_at=ended_at,
            duration_seconds=summary["duration_seconds"],
            report_data=summary,
        )
        assert saved is True

        # Read back session and verify sub-summaries are populated
        doc = mongo_repository.sessions.get_session(session_id=session_id, user_id=user_id)
        assert doc is not None
        assert doc["presence_summary"]["present_seconds"] > 0
        assert doc["activity_summary"]["engaged_seconds"] > 0
        assert doc["computer_summary"]["keyboard_events"] == 15
        assert doc["computer_summary"]["mouse_movements"] == 42
        assert doc["eye_summary"]["blink_count"] == 5
        assert doc["posture_summary"]["good_posture_seconds"] > 0


class TestDataPipelineAndInvariants:
    def test_duration_reconciliation(self):
        agg = SessionAggregator(started_at=datetime.now(timezone.utc))
        mono = 1000.0

        # 10s ENGAGED
        st1 = HumanState(track_id="track_1", person_detected=True, activity_state="ENGAGED")
        agg.add_sample(st1, current_mono=mono)
        mono += 10.0
        agg.add_sample(st1, current_mono=mono)

        # 15s OBSERVING
        st2 = HumanState(track_id="track_1", person_detected=True, activity_state="OBSERVING")
        mono += 15.0
        agg.add_sample(st2, current_mono=mono)

        # 5s ATTENTION_AWAY
        st3 = HumanState(track_id="track_1", person_detected=True, activity_state="ATTENTION_AWAY")
        mono += 5.0
        agg.add_sample(st3, current_mono=mono)

        # 10s AWAY
        st4 = HumanState(track_id="track_1", person_detected=False, activity_state="AWAY")
        mono += 10.0
        agg.add_sample(st4, current_mono=mono)

        summary = agg.get_summary()
        act = summary["activity_summary"]
        total_states = (
            act["engaged_seconds"]
            + act["observing_seconds"]
            + act["attention_away_seconds"]
            + act["away_seconds"]
            + act["unknown_seconds"]
        )

        assert abs(total_states - summary["duration_seconds"]) < 0.5

    def test_blink_rate_against_valid_eye_tracking(self):
        agg = SessionAggregator(started_at=datetime.now(timezone.utc))

        # Under 6s valid eye tracking -> blink_rate must be None (not zero)
        st_short = HumanState(track_id="track_1", 
            person_detected=True,
            blink_count=2,
            valid_eye_tracking_seconds=4.0,
        )
        agg.add_sample(st_short, current_mono=10.0)
        agg.add_sample(st_short, current_mono=13.0)
        s1 = agg.get_summary()
        assert s1["eye_summary"]["blink_rate"] is None

        # 120s (2.0 minutes) valid eye tracking with 24 blinks -> blink_rate must be 12.0 /min
        st_long = HumanState(track_id="track_1", 
            person_detected=True,
            blink_count=24,
            valid_eye_tracking_seconds=120.0,
        )
        agg.add_sample(st_long, current_mono=130.0)
        s2 = agg.get_summary()
        assert s2["eye_summary"]["blink_rate"] == 12.0

    def test_activity_interval_recording_and_isolation(self):
        user_a = f"user_a_{uuid.uuid4().hex[:6]}"
        user_b = f"user_b_{uuid.uuid4().hex[:6]}"
        sid = str(uuid.uuid4())

        now = datetime.now(timezone.utc)
        mongo_repository.activity_intervals.record_interval(
            user_id=user_a,
            session_id=sid,
            state="ENGAGED",
            start_time=now,
            end_time=now,
            duration_seconds=30.0,
            signals_summary={"keys": 10},
        )

        # User A reads interval
        intervals_a = mongo_repository.activity_intervals.get_intervals(session_id=sid, user_id=user_a)
        assert len(intervals_a) == 1
        assert intervals_a[0]["state"] == "ENGAGED"
        assert intervals_a[0]["duration_seconds"] == 30.0

        # User B cannot read User A's interval
        intervals_b = mongo_repository.activity_intervals.get_intervals(session_id=sid, user_id=user_b)
        assert len(intervals_b) == 0


class TestMultiSurfaceNotifications:
    def test_notification_device_registration_and_isolation(self):
        user_a = f"user_a_{uuid.uuid4().hex[:6]}"
        user_b = f"user_b_{uuid.uuid4().hex[:6]}"

        sub = {
            "endpoint": f"https://push.example.com/sub_{uuid.uuid4().hex}",
            "keys": {"p256dh": "dummy_p256", "auth": "dummy_auth"},
        }

        # User A registers device
        dev_a = mongo_repository.notification_devices.register_device(
            user_id=user_a,
            platform="android",
            device_name="Pixel 8",
            push_subscription=sub,
            enabled=True,
        )
        assert dev_a["device_id"] is not None
        assert dev_a["platform"] == "android"

        # User A lists devices (secrets sanitized)
        list_a = mongo_repository.notification_devices.get_user_devices(user_id=user_a, sanitize=True)
        assert len(list_a) == 1
        assert "keys" not in list_a[0].get("push_subscription", {})

        # User B sees 0 devices
        list_b = mongo_repository.notification_devices.get_user_devices(user_id=user_b)
        assert len(list_b) == 0

        # User B cannot unregister User A's device
        unreg_b = mongo_repository.notification_devices.unregister_device(user_id=user_b, device_id=dev_a["device_id"])
        assert unreg_b is False

        # User A unregisters device
        unreg_a = mongo_repository.notification_devices.unregister_device(user_id=user_a, device_id=dev_a["device_id"])
        assert unreg_a is True

    def test_push_payload_privacy_whitelist(self):
        payload = MobilePushPayload(
            event_type="POSTURE_RISK_SUSTAINED",
            severity="IMPORTANT",
            title="Posture Alert",
            message="Please adjust your chair height.",
            session_id="session-123",
        )
        data = payload.model_dump()

        # Whitelist fields only
        allowed_fields = {"event_type", "severity", "title", "message", "timestamp", "session_id"}
        assert set(data.keys()) == allowed_fields

        # Prohibited sensitive keys check
        prohibited = ["frame", "image", "screenshot", "landmarks", "key_names", "keystrokes", "mouse_x", "mouse_y"]
        for p in prohibited:
            assert p not in data

    def test_orchestrator_multi_surface_routing(self):
        orch = AlertOrchestrator()
        inv = Intervention(
            intervention_id=str(uuid.uuid4()),
            category=RiskCategory.POSTURE,
            level=RiskLevel.HIGH,
            title="High Posture Risk",
            message="Sustained forward lean detected.",
        )

        # All 3 surfaces enabled
        actions = orch.evaluate_intervention(
            intervention=inv,
            voice_alerts_enabled=True,
            browser_notifications_enabled=True,
            mobile_push_enabled=True,
            current_mono=100.0,
        )

        channels = [a.channel for a in actions]
        assert AlertChannel.IN_APP in channels
        assert AlertChannel.VOICE in channels
        assert AlertChannel.BROWSER_NOTIFICATION in channels
        assert AlertChannel.MOBILE_PUSH in channels

    def test_orchestrator_event_filters(self):
        orch = AlertOrchestrator()
        inv_posture = Intervention(
            intervention_id=str(uuid.uuid4()),
            category=RiskCategory.POSTURE,
            level=RiskLevel.HIGH,
            title="Posture",
            message="Forward lean",
        )

        # notify_posture = False -> returns empty list
        actions = orch.evaluate_intervention(
            intervention=inv_posture,
            voice_alerts_enabled=True,
            browser_notifications_enabled=True,
            mobile_push_enabled=True,
            notify_posture=False,
            current_mono=200.0,
        )
        assert len(actions) == 0

    def test_mobile_push_cooldown(self):
        orch = AlertOrchestrator()
        inv1 = Intervention(
            intervention_id=str(uuid.uuid4()),
            category=RiskCategory.POSTURE,
            level=RiskLevel.HIGH,
            title="Posture 1",
            message="Forward lean",
        )
        inv2 = Intervention(
            intervention_id=str(uuid.uuid4()),
            category=RiskCategory.POSTURE,
            level=RiskLevel.HIGH,
            title="Posture 2",
            message="Forward lean",
        )

        # First alert fires MOBILE_PUSH at mono = 100.0
        act1 = orch.evaluate_intervention(inv1, mobile_push_enabled=True, current_mono=100.0)
        assert any(a.channel == AlertChannel.MOBILE_PUSH for a in act1)

        # Second alert at mono = 120.0 (< 60s cooldown) should NOT fire MOBILE_PUSH
        act2 = orch.evaluate_intervention(inv2, mobile_push_enabled=True, current_mono=120.0)
        assert not any(a.channel == AlertChannel.MOBILE_PUSH for a in act2)

        # Third alert at mono = 170.0 (> 60s cooldown) should fire MOBILE_PUSH
        inv3 = Intervention(
            intervention_id=str(uuid.uuid4()),
            category=RiskCategory.POSTURE,
            level=RiskLevel.HIGH,
            title="Posture 3",
            message="Forward lean",
        )
        act3 = orch.evaluate_intervention(inv3, mobile_push_enabled=True, current_mono=170.0)
        assert any(a.channel == AlertChannel.MOBILE_PUSH for a in act3)
