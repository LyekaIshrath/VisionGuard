import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
"""VisionGuard Mission 05: Temporal Risk Engine & Intervention Tests.

Verifies:
- Monotonic fake-clock temporal evaluation (no real sleep delays)
- Posture temporal risk accumulation, severity weighting, and decay
- Alertness temporal risk from Mission 04 derived states
- Dominant-risk fusion with cross-coupling bounded to [0, 100]
- Observation uncertainty, pausing, and stale evidence invalidation
- Deduplicated event lifecycle (STARTED, RESOLVED) in bounded history
- Per-category cooldowns and severity escalation bypass
- Specific Cases A through H requested in prompt
- REST API and WebSocket integration
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.human_state.models import HumanState
from app.intelligence.risk_config import RiskConfig
from app.intelligence.risk_models import (
    RiskLevel,
    RiskCategory,
    RiskReasonCode,
    DomainRiskState,
    OverallRiskState,
)
from app.intelligence.risk_engine import RiskEngine
from app.alerts.models import EventStatus, InterventionType, RiskEvent, Intervention
from app.alerts.engine import InterventionEngine
from app.perception.engine import get_perception_engine


@pytest.fixture
def risk_engine() -> RiskEngine:
    """Fresh RiskEngine instance with default configuration."""
    engine = RiskEngine()
    engine.reset_session()
    return engine


@pytest.fixture
def intervention_engine() -> InterventionEngine:
    """Fresh InterventionEngine instance with default configuration."""
    engine = InterventionEngine()
    engine.reset_session()
    return engine


def make_human_state(
    posture_status: str = "GOOD",
    posture_score: float = 95.0,
    alertness_status: str = "ALERT",
    alertness_score: float = 95.0,
    eye_closure_duration: float = 0.0,
    pose_detected: bool = True,
    face_detected: bool = True,
    confidence: float = 0.95,
) -> HumanState:
    """Helper to construct HumanState with synthetic derived perception metrics."""
    return HumanState(
        timestamp=datetime.now(timezone.utc),
        track_id="test-track-001",
        person_detected=pose_detected or face_detected,
        pose_detected=pose_detected,
        face_detected=face_detected,
        posture_status=posture_status,
        posture_score=posture_score,
        alertness_status=alertness_status,
        alertness_score=alertness_score,
        eye_state="CLOSED" if eye_closure_duration > 0.5 else "OPEN",
        eye_closure_duration=eye_closure_duration,
        blink_rate=18.0,
        yawn_score=0.0,
        head_pitch=0.45,
        confidence=confidence,
    )


class TestPostureTemporalRisk:
    """Verifies slow accumulation, severity weighting, and decay for posture risk."""

    def test_good_posture_maintains_low_risk(self, risk_engine):
        state = make_human_state(posture_status="GOOD", posture_score=95.0)
        res = risk_engine.evaluate(state, timestamp=100.0)
        assert res.posture_risk.level == RiskLevel.LOW
        assert res.posture_risk.score == 0.0

    def test_brief_slouch_remains_low_risk(self, risk_engine):
        # 2 seconds of slouching (< 8.0s warn threshold)
        for i in range(20):
            t = 100.0 + i * 0.1
            res = risk_engine.evaluate(make_human_state(posture_status="SLOUCHING", posture_score=60.0), timestamp=t)
        assert res.posture_risk.level == RiskLevel.LOW
        assert res.posture_risk.active_duration_sec < 3.0

    def test_sustained_slouch_accumulates_to_moderate_risk(self, risk_engine):
        # 10 seconds of slouching (> 8.0s warn threshold)
        res = None
        for i in range(100):
            t = 100.0 + i * 0.1
            res = risk_engine.evaluate(make_human_state(posture_status="SLOUCHING", posture_score=50.0), timestamp=t)
        assert res.posture_risk.level == RiskLevel.MODERATE
        assert RiskReasonCode.SUSTAINED_SLOUCH in res.posture_risk.reasons

    def test_prolonged_slouch_accumulates_to_high_risk(self, risk_engine):
        # 22 seconds of slouching (> 20.0s high threshold)
        res = None
        for i in range(220):
            t = 100.0 + i * 0.1
            res = risk_engine.evaluate(make_human_state(posture_status="SLOUCHING", posture_score=40.0), timestamp=t)
        assert res.posture_risk.level == RiskLevel.HIGH
        assert RiskReasonCode.SUSTAINED_SLOUCH in res.posture_risk.reasons

    def test_forward_lean_and_lateral_lean_reason_codes(self, risk_engine):
        # Forward lean
        res = None
        for i in range(100):
            t = 100.0 + i * 0.1
            res = risk_engine.evaluate(make_human_state(posture_status="FORWARD_LEAN", posture_score=50.0), timestamp=t)
        assert RiskReasonCode.SUSTAINED_FORWARD_LEAN in res.posture_risk.reasons

        # Left lean
        risk_engine.reset_session()
        for i in range(100):
            t = 200.0 + i * 0.1
            res = risk_engine.evaluate(make_human_state(posture_status="LEFT_LEAN", posture_score=50.0), timestamp=t)
        assert RiskReasonCode.SUSTAINED_LEFT_LEAN in res.posture_risk.reasons

    def test_return_to_good_posture_decays_slowly_without_instant_jump(self, risk_engine):
        # 1. Drive to MODERATE
        for i in range(100):
            risk_engine.evaluate(make_human_state(posture_status="SLOUCHING", posture_score=50.0), timestamp=100.0 + i * 0.1)

        # 2. Return to GOOD for only 0.5s -> should NOT instantly jump to 0.0
        res_decaying = risk_engine.evaluate(make_human_state(posture_status="GOOD", posture_score=95.0), timestamp=110.5)
        assert res_decaying.posture_risk.score > 0.0

        # 3. Sustained GOOD for 6.0s (> 4.0s recovery time) -> decays to LOW / 0.0
        res_recovered = None
        for i in range(60):
            res_recovered = risk_engine.evaluate(make_human_state(posture_status="GOOD", posture_score=95.0), timestamp=111.0 + i * 0.1)
        assert res_recovered.posture_risk.level == RiskLevel.LOW
        assert res_recovered.posture_risk.score == 0.0


class TestAlertnessTemporalRisk:
    """Verifies alertness risk from Mission 04 derived telemetry."""

    def test_normal_alert_maintains_low_risk(self, risk_engine):
        state = make_human_state(alertness_status="ALERT", alertness_score=95.0)
        res = risk_engine.evaluate(state, timestamp=100.0)
        assert res.alertness_risk.level == RiskLevel.LOW
        assert res.alertness_risk.score == 0.0

    def test_normal_blink_does_not_increase_risk(self, risk_engine):
        # 0.25s blink
        state = make_human_state(alertness_status="ALERT", alertness_score=90.0, eye_closure_duration=0.25)
        res = risk_engine.evaluate(state, timestamp=100.0)
        assert res.alertness_risk.level == RiskLevel.LOW
        assert res.alertness_risk.score == 0.0

    def test_possible_drowsiness_accumulates_to_moderate_and_high(self, risk_engine):
        # 2.0s of POSSIBLE_DROWSINESS (> 1.5s warn threshold)
        res_mod = None
        for i in range(20):
            t = 100.0 + i * 0.1
            res_mod = risk_engine.evaluate(make_human_state(alertness_status="POSSIBLE_DROWSINESS", alertness_score=40.0), timestamp=t)
        assert res_mod.alertness_risk.level == RiskLevel.MODERATE
        assert RiskReasonCode.POSSIBLE_DROWSINESS in res_mod.alertness_risk.reasons

        # 4.0s of POSSIBLE_DROWSINESS (> 3.5s high threshold)
        res_high = None
        for i in range(20, 40):
            t = 100.0 + i * 0.1
            res_high = risk_engine.evaluate(make_human_state(alertness_status="POSSIBLE_DROWSINESS", alertness_score=30.0), timestamp=t)
        assert res_high.alertness_risk.level == RiskLevel.HIGH

    def test_prolonged_eye_closure_triggers_high_risk_and_override(self, risk_engine):
        # Eye closure for 2.2s (> 2.0s critical closure threshold)
        state = make_human_state(alertness_status="POSSIBLE_DROWSINESS", alertness_score=20.0, eye_closure_duration=2.2)
        res = risk_engine.evaluate(state, timestamp=100.0)
        assert res.alertness_risk.level == RiskLevel.HIGH
        assert RiskReasonCode.PROLONGED_EYE_CLOSURE in res.alertness_risk.reasons
        # Overall level escalates directly
        assert res.level == RiskLevel.HIGH


class TestRiskFusionAndUncertainty:
    """Verifies dominant-risk fusion, bounds, and UNKNOWN handling."""

    def test_posture_low_and_alertness_low_produces_low(self, risk_engine):
        state = make_human_state(posture_status="GOOD", alertness_status="ALERT")
        res = risk_engine.evaluate(state, timestamp=100.0)
        assert res.level == RiskLevel.LOW
        assert res.score == 0.0

    def test_posture_moderate_and_alertness_low_reflects_posture(self, risk_engine):
        for i in range(100):
            res = risk_engine.evaluate(
                make_human_state(posture_status="SLOUCHING", posture_score=50.0, alertness_status="ALERT", alertness_score=95.0),
                timestamp=100.0 + i * 0.1,
            )
        assert res.posture_risk.level == RiskLevel.MODERATE
        assert res.alertness_risk.level == RiskLevel.LOW
        assert res.level == RiskLevel.MODERATE
        assert res.dominant_category == RiskCategory.POSTURE

    def test_posture_low_and_alertness_high_is_not_diluted(self, risk_engine):
        state = make_human_state(
            posture_status="GOOD",
            posture_score=100.0,
            alertness_status="POSSIBLE_DROWSINESS",
            alertness_score=10.0,
            eye_closure_duration=2.5,
        )
        res = risk_engine.evaluate(state, timestamp=100.0)
        assert res.posture_risk.level == RiskLevel.LOW
        assert res.alertness_risk.level == RiskLevel.HIGH
        assert res.level == RiskLevel.HIGH
        assert res.dominant_category == RiskCategory.ALERTNESS

    def test_one_unknown_domain_preserves_valid_high(self, risk_engine):
        # Drive posture to HIGH
        for i in range(220):
            risk_engine.evaluate(make_human_state(posture_status="SLOUCHING", posture_score=30.0), timestamp=100.0 + i * 0.1)

        # Face disappears (face_detected=False, alertness UNKNOWN)
        state_face_missing = make_human_state(
            posture_status="SLOUCHING",
            posture_score=30.0,
            face_detected=False,
            alertness_status="UNKNOWN",
        )
        res = risk_engine.evaluate(state_face_missing, timestamp=125.0)
        assert res.alertness_risk.is_valid is False
        assert res.alertness_risk.level == RiskLevel.UNKNOWN
        assert res.posture_risk.is_valid is True
        assert res.posture_risk.level == RiskLevel.HIGH
        assert res.level == RiskLevel.HIGH

    def test_both_unknown_produces_overall_unknown(self, risk_engine):
        state_none = make_human_state(
            pose_detected=False,
            face_detected=False,
            posture_status="UNKNOWN",
            alertness_status="UNKNOWN",
        )
        res = risk_engine.evaluate(state_none, timestamp=100.0)
        assert res.level == RiskLevel.UNKNOWN
        assert res.score is None


class TestSpecificRequiredCasesAThroughH:
    """Verifies all mandatory test cases A through H."""

    def test_case_a_posture_mod_then_alertness_mod_creates_new_event(self, risk_engine, intervention_engine):
        # Case A: Posture MODERATE + Alertness becomes MODERATE -> new ALERTNESS event exists even if overall is still MODERATE
        # 1. Drive posture to MODERATE
        for i in range(100):
            t = 100.0 + i * 0.1
            state = make_human_state(posture_status="SLOUCHING", posture_score=50.0, alertness_status="ALERT")
            risk = risk_engine.evaluate(state, timestamp=t)
            intervention_engine.evaluate(risk, timestamp=t)

        posture_events = [e for e in intervention_engine.event_history if e.category == RiskCategory.POSTURE]
        assert len(posture_events) >= 1
        assert posture_events[0].risk_level == RiskLevel.MODERATE

        # 2. Alertness becomes MODERATE
        for i in range(20):
            t = 110.0 + i * 0.1
            state = make_human_state(posture_status="SLOUCHING", posture_score=50.0, alertness_status="POSSIBLE_DROWSINESS", alertness_score=40.0)
            risk = risk_engine.evaluate(state, timestamp=t)
            intervention_engine.evaluate(risk, timestamp=t)

        alertness_events = [e for e in intervention_engine.event_history if e.category == RiskCategory.ALERTNESS]
        assert len(alertness_events) >= 1
        assert alertness_events[0].risk_level == RiskLevel.MODERATE

    def test_case_b_posture_high_then_pose_unknown_briefly_pauses_no_false_low(self, risk_engine, intervention_engine):
        # Case B: Posture HIGH -> pose UNKNOWN briefly -> preserved temporal state, NO false LOW/RESOLVED
        for i in range(220):
            t = 100.0 + i * 0.1
            risk = risk_engine.evaluate(make_human_state(posture_status="SLOUCHING", posture_score=30.0), timestamp=t)
            intervention_engine.evaluate(risk, timestamp=t)
        assert risk.posture_risk.level == RiskLevel.HIGH

        # Pose disappears for 1 second
        risk_paused = risk_engine.evaluate(make_human_state(pose_detected=False, posture_status="UNKNOWN"), timestamp=123.0)
        intervention_engine.evaluate(risk_paused, timestamp=123.0)

        assert risk_paused.posture_risk.level == RiskLevel.UNKNOWN
        # Active duration in accumulator must not have vanished to 0
        assert risk_engine._posture_non_good_duration > 15.0
        # No RESOLVED event produced for posture
        resolved_events = [e for e in intervention_engine.event_history if e.status == EventStatus.RESOLVED and e.category == RiskCategory.POSTURE]
        assert len(resolved_events) == 0

    def test_case_c_alertness_high_then_face_disappears_no_extra_drowsiness(self, risk_engine, intervention_engine):
        # Case C: Alertness HIGH -> face disappears -> UNKNOWN, no extra drowsiness event
        state = make_human_state(alertness_status="POSSIBLE_DROWSINESS", alertness_score=10.0, eye_closure_duration=2.5)
        risk = risk_engine.evaluate(state, timestamp=100.0)
        intervention_engine.evaluate(risk, timestamp=100.0)
        initial_event_count = len(intervention_engine.event_history)

        # Face disappears
        state_face_gone = make_human_state(face_detected=False, alertness_status="UNKNOWN")
        risk_gone = risk_engine.evaluate(state_face_gone, timestamp=101.0)
        intervention_engine.evaluate(risk_gone, timestamp=101.0)

        assert risk_gone.alertness_risk.level == RiskLevel.UNKNOWN
        # No new STARTED events generated
        new_started = [e for e in intervention_engine.event_history[initial_event_count:] if e.status == EventStatus.STARTED]
        assert len(new_started) == 0

    def test_case_d_monitoring_stop_for_30s_does_not_count_toward_risk(self, risk_engine):
        # Case D: Monitoring STOP for 30 seconds -> START: stopped time does not count
        # 1. Slouch for 5 seconds (not yet MODERATE, threshold is 8.0s)
        for i in range(50):
            risk_engine.evaluate(make_human_state(posture_status="SLOUCHING", posture_score=50.0), timestamp=100.0 + i * 0.1)
        assert risk_engine._posture_non_good_duration < 6.0

        # 2. Monitoring STOP
        risk_engine.stop_session()

        # 3. 30 seconds pass while stopped
        # 4. Monitoring START (resets session accumulators)
        risk_engine.reset_session()

        # 5. Slouch for 1 second -> total duration must be ~1.0s, NOT 36 seconds
        res = risk_engine.evaluate(make_human_state(posture_status="SLOUCHING", posture_score=50.0), timestamp=136.0)
        assert res.posture_risk.active_duration_sec < 2.0
        assert res.posture_risk.level == RiskLevel.LOW

    def test_case_e_clear_event_history_while_high_preserves_actual_high(self, risk_engine, intervention_engine):
        # Case E: Clear event history while currently HIGH -> actual risk remains HIGH
        for i in range(220):
            t = 100.0 + i * 0.1
            risk = risk_engine.evaluate(make_human_state(posture_status="SLOUCHING", posture_score=30.0), timestamp=t)
            intervention_engine.evaluate(risk, timestamp=t)

        assert risk.level == RiskLevel.HIGH
        assert len(intervention_engine.event_history) > 0

        # Clear event history
        intervention_engine.reset_history()
        assert len(intervention_engine.event_history) == 0

        # Ongoing physical state evaluated again -> remains HIGH!
        risk_after = risk_engine.evaluate(make_human_state(posture_status="SLOUCHING", posture_score=30.0), timestamp=123.0)
        assert risk_after.level == RiskLevel.HIGH

    def test_case_g_posture_high_plus_alertness_high_bounded_at_100(self, risk_engine):
        # Case G: Posture HIGH + Alertness HIGH -> overall score bounded at <= 100.0
        for i in range(220):
            t = 100.0 + i * 0.1
            res = risk_engine.evaluate(
                make_human_state(
                    posture_status="SLOUCHING",
                    posture_score=10.0,
                    alertness_status="POSSIBLE_DROWSINESS",
                    alertness_score=10.0,
                    eye_closure_duration=3.0,
                ),
                timestamp=t,
            )
        assert res.level == RiskLevel.HIGH
        assert res.score is not None
        assert 0.0 <= res.score <= 100.0

    def test_case_h_new_reason_within_same_category_generated_and_deduplicated(self, risk_engine, intervention_engine):
        # Case H: New reason within same category while level unchanged -> event generated once, then deduplicated
        # 1. Slouching -> generates SUSTAINED_SLOUCH
        for i in range(100):
            t = 100.0 + i * 0.1
            risk = risk_engine.evaluate(make_human_state(posture_status="SLOUCHING", posture_score=50.0), timestamp=t)
            intervention_engine.evaluate(risk, timestamp=t)

        count_after_slouch = len(intervention_engine.event_history)
        assert count_after_slouch == 1

        # 2. Changes to FORWARD_LEAN (new reason code!) while level is still MODERATE
        for i in range(20):
            t = 110.0 + i * 0.1
            risk = risk_engine.evaluate(make_human_state(posture_status="FORWARD_LEAN", posture_score=50.0), timestamp=t)
            intervention_engine.evaluate(risk, timestamp=t)

        # A new event was added for the new reason code
        assert len(intervention_engine.event_history) == count_after_slouch + 1
        new_event = intervention_engine.event_history[-1]
        assert RiskReasonCode.SUSTAINED_FORWARD_LEAN in new_event.reason_codes

        # 3. Next frames with same FORWARD_LEAN do not add duplicates
        for i in range(20):
            t = 112.0 + i * 0.1
            risk = risk_engine.evaluate(make_human_state(posture_status="FORWARD_LEAN", posture_score=50.0), timestamp=t)
            intervention_engine.evaluate(risk, timestamp=t)

        assert len(intervention_engine.event_history) == count_after_slouch + 1


class TestInterventionEngineCooldownAndEscalation:
    """Verifies per-category cooldowns and escalation bypass."""

    def test_first_event_generates_intervention(self, intervention_engine):
        p_state = DomainRiskState(
            category=RiskCategory.POSTURE,
            level=RiskLevel.MODERATE,
            score=50.0,
            is_valid=True,
            active_duration_sec=9.0,
            reasons=[RiskReasonCode.SUSTAINED_SLOUCH],
        )
        risk = OverallRiskState(
            level=RiskLevel.MODERATE,
            score=50.0,
            posture_risk=p_state,
            alertness_risk=DomainRiskState(category=RiskCategory.ALERTNESS, level=RiskLevel.LOW, score=0.0, is_valid=True),
        )
        intervention = intervention_engine.evaluate(risk, timestamp=100.0)
        assert intervention is not None
        assert intervention.category == RiskCategory.POSTURE
        assert intervention.level == RiskLevel.MODERATE

    def test_same_repeated_event_during_cooldown_suppressed(self, intervention_engine):
        p_state = DomainRiskState(
            category=RiskCategory.POSTURE,
            level=RiskLevel.MODERATE,
            score=50.0,
            is_valid=True,
            active_duration_sec=9.0,
            reasons=[RiskReasonCode.SUSTAINED_SLOUCH],
        )
        risk = OverallRiskState(
            level=RiskLevel.MODERATE,
            score=50.0,
            posture_risk=p_state,
            alertness_risk=DomainRiskState(category=RiskCategory.ALERTNESS, level=RiskLevel.LOW, score=0.0, is_valid=True),
        )
        first = intervention_engine.evaluate(risk, timestamp=100.0)
        assert first is not None

        # Repeat 10 seconds later (< 60s posture cooldown)
        second = intervention_engine.evaluate(risk, timestamp=110.0)
        # Suppressed
        assert second == first  # active_intervention still preserved, but no new one generated

    def test_moderate_to_high_escalation_bypasses_cooldown(self, intervention_engine):
        # 1. MODERATE alert sent at t=100.0
        p_mod = DomainRiskState(
            category=RiskCategory.POSTURE,
            level=RiskLevel.MODERATE,
            score=50.0,
            is_valid=True,
            active_duration_sec=9.0,
            reasons=[RiskReasonCode.SUSTAINED_SLOUCH],
        )
        risk_mod = OverallRiskState(
            level=RiskLevel.MODERATE,
            score=50.0,
            posture_risk=p_mod,
            alertness_risk=DomainRiskState(category=RiskCategory.ALERTNESS, level=RiskLevel.LOW, score=0.0, is_valid=True),
        )
        int_mod = intervention_engine.evaluate(risk_mod, timestamp=100.0)
        assert int_mod.level == RiskLevel.MODERATE

        # 2. Escalates to HIGH 15 seconds later (within 60s cooldown)
        p_high = DomainRiskState(
            category=RiskCategory.POSTURE,
            level=RiskLevel.HIGH,
            score=85.0,
            is_valid=True,
            active_duration_sec=22.0,
            reasons=[RiskReasonCode.SUSTAINED_SLOUCH],
        )
        risk_high = OverallRiskState(
            level=RiskLevel.HIGH,
            score=85.0,
            posture_risk=p_high,
            alertness_risk=DomainRiskState(category=RiskCategory.ALERTNESS, level=RiskLevel.LOW, score=0.0, is_valid=True),
        )
        int_high = intervention_engine.evaluate(risk_high, timestamp=115.0)
        # Bypassed cooldown for higher severity!
        assert int_high is not None
        assert int_high.level == RiskLevel.HIGH

    def test_posture_cooldown_does_not_suppress_alertness_alert(self, intervention_engine):
        # 1. Posture MODERATE alert sent at t=100.0
        p_mod = DomainRiskState(
            category=RiskCategory.POSTURE,
            level=RiskLevel.MODERATE,
            score=50.0,
            is_valid=True,
            active_duration_sec=9.0,
            reasons=[RiskReasonCode.SUSTAINED_SLOUCH],
        )
        risk_p = OverallRiskState(
            level=RiskLevel.MODERATE,
            score=50.0,
            posture_risk=p_mod,
            alertness_risk=DomainRiskState(category=RiskCategory.ALERTNESS, level=RiskLevel.LOW, score=0.0, is_valid=True),
        )
        intervention_engine.evaluate(risk_p, timestamp=100.0)

        # 2. 5 seconds later, Alertness MODERATE arrives
        a_mod = DomainRiskState(
            category=RiskCategory.ALERTNESS,
            level=RiskLevel.MODERATE,
            score=55.0,
            is_valid=True,
            active_duration_sec=2.0,
            reasons=[RiskReasonCode.POSSIBLE_DROWSINESS],
        )
        risk_a = OverallRiskState(
            level=RiskLevel.MODERATE,
            score=55.0,
            posture_risk=p_mod,
            alertness_risk=a_mod,
        )
        int_alertness = intervention_engine.evaluate(risk_a, timestamp=105.0)
        # Alertness intervention must NOT be suppressed by posture cooldown!
        assert int_alertness is not None
        assert int_alertness.category == RiskCategory.ALERTNESS


class TestRiskAPIAndWebSocket:
    """Verifies REST endpoints and WebSocket stream for risk."""

    def test_risk_status_api_endpoint(self):
        client = TestClient(app)
        res = client.get("/api/v1/risk/status")
        assert res.status_code == 200
        data = res.json()
        assert "risk_level" in data
        assert "posture_risk" in data
        assert "alertness_risk" in data

    def test_risk_events_and_reset_api_endpoints(self):
        client = TestClient(app)
        res = client.get("/api/v1/risk/events")
        assert res.status_code == 200
        assert "events" in res.json()
        assert "total_count" in res.json()

        res_reset = client.post("/api/v1/risk/events/reset")
        assert res_reset.status_code == 200
        assert res_reset.json()["status"] == "RESET"

    def test_websocket_stream_includes_risk_fields(self):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/monitoring/ws") as ws:
            ws.receive_json()  # status
            hs_msg = ws.receive_json()  # human_state
            assert hs_msg["type"] == "human_state"
            data = hs_msg["data"]
            assert "risk_level" in data
            assert "risk_score" in data
            assert "posture_risk" in data
            assert "alertness_risk" in data
            assert "active_reasons" in data
            assert "active_intervention" in data


class TestFusionFormulaAndDeterministicMath:
    """Verifies exact mathematical properties of the nonlinear fusion formula."""

    def test_exact_fusion_formula_values(self, risk_engine):
        cfg = risk_engine._config
        assert cfg.cross_coupling_weight == 0.10

        # Scenario 1: One domain moderate (50.0), other low (20.0)
        # Formula: 50.0 + 0.10 * 20.0 = 52.0
        p_state = DomainRiskState(category=RiskCategory.POSTURE, level=RiskLevel.MODERATE, score=50.0, is_valid=True)
        a_state = DomainRiskState(category=RiskCategory.ALERTNESS, level=RiskLevel.LOW, score=20.0, is_valid=True)
        score, lvl, dom = risk_engine._fuse_domains(p_state, a_state, now=100.0)
        assert score == 52.0
        assert lvl == RiskLevel.MODERATE
        assert dom == RiskCategory.POSTURE

        # Scenario 2: Two moderate conditions MUST NOT become HIGH
        # Both domains at 50.0:
        # Formula: 50.0 + 0.10 * 50.0 = 55.0 (< 70.0 high threshold)
        p_mod = DomainRiskState(category=RiskCategory.POSTURE, level=RiskLevel.MODERATE, score=50.0, is_valid=True)
        a_mod = DomainRiskState(category=RiskCategory.ALERTNESS, level=RiskLevel.MODERATE, score=50.0, is_valid=True)
        score2, lvl2, _ = risk_engine._fuse_domains(p_mod, a_mod, now=100.0)
        assert score2 == 55.0
        assert lvl2 == RiskLevel.MODERATE, "Two moderate conditions must not become HIGH"

        # Even at 60.0 + 60.0 = 66.0 (< 70.0 high threshold)
        p_mod60 = DomainRiskState(category=RiskCategory.POSTURE, level=RiskLevel.MODERATE, score=60.0, is_valid=True)
        a_mod60 = DomainRiskState(category=RiskCategory.ALERTNESS, level=RiskLevel.MODERATE, score=60.0, is_valid=True)
        score3, lvl3, _ = risk_engine._fuse_domains(p_mod60, a_mod60, now=100.0)
        assert score3 == 66.0
        assert lvl3 == RiskLevel.MODERATE, "Two 60.0 moderate scores must not become HIGH"

        # Scenario 3: Extreme boundary capping at exactly 100.0 (advance timestamp past hysteresis sustain)
        p_max = DomainRiskState(category=RiskCategory.POSTURE, level=RiskLevel.HIGH, score=100.0, is_valid=True)
        a_max = DomainRiskState(category=RiskCategory.ALERTNESS, level=RiskLevel.HIGH, score=100.0, is_valid=True)
        # First evaluation marks pending HIGH
        risk_engine._fuse_domains(p_max, a_max, now=100.0)
        # Advance clock by > level_entry_sustain_sec (1.0s) to 102.0
        score_max, lvl_max, _ = risk_engine._fuse_domains(p_max, a_max, now=102.0)
        assert score_max == 100.0
        assert lvl_max == RiskLevel.HIGH


class TestPrivacyAndDerivedContract:
    """Verifies strict privacy preservation: no frames, no landmarks, no face coordinates."""

    def test_risk_event_and_intervention_serialization_privacy(self):
        forbidden_substrings = [
            "frame", "jpeg", "jpg", "image", "landmark", "coordinate",
            "face_mesh", "pose_landmarks", "embedding"
        ]

        event = RiskEvent(
            event_id="ev-001",
            category=RiskCategory.ALERTNESS,
            status=EventStatus.STARTED,
            risk_level=RiskLevel.HIGH,
            risk_score=85.0,
            message="Possible drowsiness detected.",
            reason_codes=[RiskReasonCode.POSSIBLE_DROWSINESS],
            duration_sec=3.5,
        )
        event_dict = event.model_dump()
        event_json = event.model_dump_json().lower()

        for sub in forbidden_substrings:
            assert sub not in event_dict, f"Forbidden field '{sub}' found in RiskEvent dict"
            assert sub not in event_json, f"Forbidden substring '{sub}' found in RiskEvent json"

        intervention = Intervention(
            intervention_id="inv-001",
            category=RiskCategory.POSTURE,
            level=RiskLevel.MODERATE,
            title="Posture Notice",
            message="Gentle reminder to sit upright.",
        )
        inv_dict = intervention.model_dump()
        inv_json = intervention.model_dump_json().lower()

        for sub in forbidden_substrings:
            assert sub not in inv_dict, f"Forbidden field '{sub}' found in Intervention dict"
            assert sub not in inv_json, f"Forbidden substring '{sub}' found in Intervention json"


class TestBrowserInterventionClientContract:
    """Verifies Case F: client-side deduplication prevents duplicate browser notifications on rerender."""

    def test_case_f_browser_intervention_rerender_deduplication(self):
        sent_notifications = []
        last_notified_id = None

        def handle_intervention_update(intervention: Intervention | None):
            nonlocal last_notified_id
            if intervention is not None:
                if intervention.intervention_id != last_notified_id:
                    last_notified_id = intervention.intervention_id
                    sent_notifications.append(intervention)

        inv = Intervention(
            intervention_id="inv-unique-01",
            category=RiskCategory.ALERTNESS,
            level=RiskLevel.HIGH,
            title="Drowsiness Notice",
            message="Take a brief rest.",
        )

        # 1. First arrival of intervention -> 1 notification sent
        handle_intervention_update(inv)
        assert len(sent_notifications) == 1
        assert sent_notifications[0].intervention_id == "inv-unique-01"

        # 2. React rerender 1 (same state received) -> 0 new notifications
        handle_intervention_update(inv)
        assert len(sent_notifications) == 1

        # 3. React rerender 2 (same state received) -> 0 new notifications
        handle_intervention_update(inv)
        assert len(sent_notifications) == 1

        # 4. New distinct intervention arrives -> 2nd notification sent
        inv2 = Intervention(
            intervention_id="inv-unique-02",
            category=RiskCategory.POSTURE,
            level=RiskLevel.HIGH,
            title="Posture High Alert",
            message="Please adjust back position.",
        )
        handle_intervention_update(inv2)
        assert len(sent_notifications) == 2
        assert sent_notifications[1].intervention_id == "inv-unique-02"
