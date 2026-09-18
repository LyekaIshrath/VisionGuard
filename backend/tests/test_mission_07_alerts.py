import os
import time
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.intelligence.risk_models import RiskCategory, RiskLevel
from app.alerts.models import (
    Intervention,
    InterventionType,
    AlertChannel,
    AlertPriority,
    RiskEvent,
    EventStatus
)
from app.alerts.policy import AlertPolicyConfig
from app.alerts.orchestrator import AlertOrchestrator
from app.auth.models import AuthenticatedUser
from app.auth.dependencies import get_current_user


def make_intervention(cat=RiskCategory.POSTURE, level=RiskLevel.MODERATE, i_id="int-test-1", msg="Adjust posture"):
    return Intervention(
        intervention_id=i_id,
        category=cat,
        level=level,
        title=f"{cat.value} alert",
        message=msg,
        type=InterventionType.IN_APP
    )


class TestAlertOrchestratorAndPolicy:
    def test_low_produces_no_voice_or_browser_alerts(self):
        orchestrator = AlertOrchestrator()
        inv = make_intervention(level=RiskLevel.LOW)
        actions = orchestrator.evaluate_intervention(
            inv, voice_alerts_enabled=True, browser_notifications_enabled=True
        )
        assert len(actions) == 0

    def test_unknown_produces_no_synthetic_alerts(self):
        orchestrator = AlertOrchestrator()
        inv = make_intervention(level=RiskLevel.UNKNOWN)
        actions = orchestrator.evaluate_intervention(
            inv, voice_alerts_enabled=True, browser_notifications_enabled=True
        )
        assert len(actions) == 0

    def test_moderate_creates_inapp_and_voice_when_enabled(self):
        orchestrator = AlertOrchestrator()
        inv = make_intervention(level=RiskLevel.MODERATE)
        actions = orchestrator.evaluate_intervention(
            inv, voice_alerts_enabled=True, browser_notifications_enabled=True
        )
        channels = {a.channel for a in actions}
        assert AlertChannel.IN_APP in channels
        assert AlertChannel.VOICE in channels
        assert AlertChannel.BROWSER_NOTIFICATION in channels

    def test_disabled_voice_produces_no_speech(self):
        orchestrator = AlertOrchestrator()
        inv = make_intervention(level=RiskLevel.HIGH)
        actions = orchestrator.evaluate_intervention(
            inv, voice_alerts_enabled=False, browser_notifications_enabled=True
        )
        channels = {a.channel for a in actions}
        assert AlertChannel.IN_APP in channels
        assert AlertChannel.VOICE not in channels
        assert AlertChannel.BROWSER_NOTIFICATION in channels

    def test_quiet_mode_suppresses_voice_and_notification_keeps_in_app(self):
        orchestrator = AlertOrchestrator()
        inv = make_intervention(level=RiskLevel.HIGH)
        actions = orchestrator.evaluate_intervention(
            inv,
            voice_alerts_enabled=True,
            browser_notifications_enabled=True,
            quiet_mode_enabled=True
        )
        channels = {a.channel for a in actions}
        assert AlertChannel.IN_APP in channels
        assert AlertChannel.VOICE not in channels
        assert AlertChannel.BROWSER_NOTIFICATION not in channels

    def test_deduplication_of_same_intervention_id(self):
        orchestrator = AlertOrchestrator()
        inv = make_intervention(level=RiskLevel.MODERATE, i_id="same-id")

        # First delivery: creates in-app, voice, notification
        actions1 = orchestrator.evaluate_intervention(
            inv, voice_alerts_enabled=True, browser_notifications_enabled=True, current_mono=100.0
        )
        assert any(a.channel == AlertChannel.VOICE for a in actions1)

        # Repeated delivery with identical intervention_id (e.g. ~10Hz WebSocket tick)
        actions2 = orchestrator.evaluate_intervention(
            inv, voice_alerts_enabled=True, browser_notifications_enabled=True, current_mono=100.1
        )
        # Should not produce repeated voice or browser notifications
        assert not any(a.channel == AlertChannel.VOICE for a in actions2)
        assert not any(a.channel == AlertChannel.BROWSER_NOTIFICATION for a in actions2)

    def test_posture_cooldown_prevents_voice_spam(self):
        orchestrator = AlertOrchestrator()
        inv1 = make_intervention(cat=RiskCategory.POSTURE, level=RiskLevel.MODERATE, i_id="p1")
        orchestrator.evaluate_intervention(
            inv1, voice_alerts_enabled=True, browser_notifications_enabled=True, current_mono=100.0
        )

        # New intervention at t=120s (20s later < 60s cooldown)
        inv2 = make_intervention(cat=RiskCategory.POSTURE, level=RiskLevel.MODERATE, i_id="p2")
        actions2 = orchestrator.evaluate_intervention(
            inv2, voice_alerts_enabled=True, browser_notifications_enabled=True, current_mono=120.0
        )
        assert not any(a.channel == AlertChannel.VOICE for a in actions2)

        # After 60s cooldown (t=165s), voice is allowed again
        inv3 = make_intervention(cat=RiskCategory.POSTURE, level=RiskLevel.MODERATE, i_id="p3")
        actions3 = orchestrator.evaluate_intervention(
            inv3, voice_alerts_enabled=True, browser_notifications_enabled=True, current_mono=165.0
        )
        assert any(a.channel == AlertChannel.VOICE for a in actions3)

    def test_posture_and_alertness_have_independent_cooldowns(self):
        orchestrator = AlertOrchestrator()
        # Posture alert at t=100s
        inv_posture = make_intervention(cat=RiskCategory.POSTURE, level=RiskLevel.MODERATE, i_id="p1")
        actions_p = orchestrator.evaluate_intervention(
            inv_posture, voice_alerts_enabled=True, browser_notifications_enabled=True, current_mono=100.0
        )
        assert any(a.channel == AlertChannel.VOICE for a in actions_p)

        # Alertness alert at t=105s (5s later) -> alertness cooldown has NOT elapsed, but alertness has NOT triggered yet!
        inv_alertness = make_intervention(cat=RiskCategory.ALERTNESS, level=RiskLevel.MODERATE, i_id="a1")
        actions_a = orchestrator.evaluate_intervention(
            inv_alertness, voice_alerts_enabled=True, browser_notifications_enabled=True, current_mono=105.0
        )
        # Independent: alertness must speak!
        assert any(a.channel == AlertChannel.VOICE for a in actions_a)

    def test_moderate_to_high_escalation_bypasses_cooldown_once(self):
        orchestrator = AlertOrchestrator()
        # Moderate posture alert at t=100s
        inv_mod = make_intervention(cat=RiskCategory.POSTURE, level=RiskLevel.MODERATE, i_id="p-mod")
        orchestrator.evaluate_intervention(
            inv_mod, voice_alerts_enabled=True, browser_notifications_enabled=True, current_mono=100.0
        )

        # Escalate to HIGH posture alert at t=110s (only 10s later, before 60s cooldown)
        inv_high = make_intervention(cat=RiskCategory.POSTURE, level=RiskLevel.HIGH, i_id="p-high")
        actions_high = orchestrator.evaluate_intervention(
            inv_high, voice_alerts_enabled=True, browser_notifications_enabled=True, current_mono=110.0
        )
        # Escalation bypasses cooldown once!
        assert any(a.channel == AlertChannel.VOICE for a in actions_high)
        assert any(a.channel == AlertChannel.BROWSER_NOTIFICATION for a in actions_high)

    def test_resolved_clears_active_presentation_no_repeated_speech(self):
        orchestrator = AlertOrchestrator()
        inv = make_intervention(cat=RiskCategory.POSTURE, level=RiskLevel.HIGH, i_id="p1")
        orchestrator.evaluate_intervention(inv, voice_alerts_enabled=True, current_mono=100.0)

        # Resolved event clears active state
        orchestrator.handle_resolution(RiskCategory.POSTURE)
        assert orchestrator._active_interventions[RiskCategory.POSTURE] is None

        # Evaluating resolved/low produces zero actions (no repeated recovery speech)
        inv_low = make_intervention(cat=RiskCategory.POSTURE, level=RiskLevel.LOW, i_id="p-res")
        actions = orchestrator.evaluate_intervention(inv_low, voice_alerts_enabled=True, current_mono=105.0)
        assert len(actions) == 0

    def test_alert_acknowledgement_hides_in_app_without_altering_risk(self):
        orchestrator = AlertOrchestrator()
        inv = make_intervention(level=RiskLevel.HIGH, i_id="ack-1")
        actions1 = orchestrator.evaluate_intervention(inv, voice_alerts_enabled=True, current_mono=100.0)
        assert any(a.channel == AlertChannel.IN_APP for a in actions1)

        # Acknowledge the alert
        orchestrator.acknowledge_alert("ack-1")
        assert orchestrator.is_acknowledged("ack-1")

        # Subsequent evaluation with same acknowledged intervention hides in-app action
        actions2 = orchestrator.evaluate_intervention(inv, voice_alerts_enabled=True, current_mono=101.0)
        assert not any(a.channel == AlertChannel.IN_APP for a in actions2)

    def test_session_reset_clears_all_transient_state(self):
        orchestrator = AlertOrchestrator()
        inv = make_intervention(level=RiskLevel.HIGH, i_id="rst-1")
        orchestrator.evaluate_intervention(inv, voice_alerts_enabled=True, current_mono=100.0)
        orchestrator.acknowledge_alert("rst-1")

        orchestrator.reset_session()
        assert len(orchestrator._dispatched_interventions) == 0
        assert len(orchestrator._acknowledged_interventions) == 0
        assert len(orchestrator._last_voice_time) == 0

    def test_calm_deterministic_phrasing(self):
        orchestrator = AlertOrchestrator()
        inv_p_mod = make_intervention(cat=RiskCategory.POSTURE, level=RiskLevel.MODERATE, i_id="m1")
        actions_p_mod = orchestrator.evaluate_intervention(inv_p_mod, voice_alerts_enabled=True)
        assert actions_p_mod[0].message == "Your posture has been off for a while. Consider adjusting your sitting position."

        orchestrator.reset_session()
        inv_p_hi = make_intervention(cat=RiskCategory.POSTURE, level=RiskLevel.HIGH, i_id="m2")
        actions_p_hi = orchestrator.evaluate_intervention(inv_p_hi, voice_alerts_enabled=True)
        assert actions_p_hi[0].message == "Your posture needs attention. Please adjust your sitting position."

        orchestrator.reset_session()
        inv_a_mod = make_intervention(cat=RiskCategory.ALERTNESS, level=RiskLevel.MODERATE, i_id="m3")
        actions_a_mod = orchestrator.evaluate_intervention(inv_a_mod, voice_alerts_enabled=True)
        assert actions_a_mod[0].message == "You appear less alert. Consider taking a short break."

        orchestrator.reset_session()
        inv_a_hi = make_intervention(cat=RiskCategory.ALERTNESS, level=RiskLevel.HIGH, i_id="m4")
        actions_a_hi = orchestrator.evaluate_intervention(inv_a_hi, voice_alerts_enabled=True)
        assert actions_a_hi[0].message == "Your alertness appears reduced. Please consider taking a break."

    def test_alert_action_privacy_zero_cv_leakage(self):
        orchestrator = AlertOrchestrator()
        inv = make_intervention(level=RiskLevel.HIGH, i_id="priv-1")
        actions = orchestrator.evaluate_intervention(inv, voice_alerts_enabled=True, browser_notifications_enabled=True)
        for act in actions:
            data = act.model_dump()
            forbidden = {"frame", "raw_frame", "image", "landmarks", "face_landmarks", "pose_landmarks", "embedding"}
            assert not any(k in data for k in forbidden)


class TestUserPreferencesApi:
    def test_unauthenticated_requests_fail(self):
        client = TestClient(app)
        res_get = client.get("/api/v1/user/preferences")
        assert res_get.status_code == 401

        res_put = client.put("/api/v1/user/preferences", json={"voice_pitch": 1.2})
        assert res_put.status_code == 401

        res_ack = client.post("/api/v1/user/alerts/acknowledge", json={"intervention_id": "test"})
        assert res_ack.status_code == 401

    def test_authenticated_user_preferences_flow(self, monkeypatch):
        fake_user = AuthenticatedUser(
            id="test-user-alerts-1",
            email="test@visionguard.local",
            role="authenticated",
            jwt_token="fake-jwt"
        )
        app.dependency_overrides[get_current_user] = lambda: fake_user
        
        # Mock repository upsert and get
        from app.sessions.service import session_service
        mock_prefs = {
            "user_id": fake_user.id,
            "voice_alerts_enabled": True,
            "voice_volume": 0.85,
            "voice_rate": 1.1,
            "voice_pitch": 1.05,
            "quiet_mode_enabled": False,
            "selected_voice": "Google UK English Male"
        }
        async def mock_upsert(user_id, token, payload):
            return {"user_id": user_id, "preferences": {**mock_prefs, **payload}}
        async def mock_get(user_id, token):
            return {"user_id": user_id, "preferences": mock_prefs}

        monkeypatch.setattr(session_service.repository, "upsert_user_preferences", mock_upsert)
        monkeypatch.setattr(session_service.repository, "get_user_preferences", mock_get)

        client = TestClient(app)

        try:
            # GET preferences
            res_get = client.get("/api/v1/user/preferences")
            assert res_get.status_code == 200
            assert res_get.json()["preferences"]["voice_pitch"] == 1.05

            # PUT valid preferences
            res_put = client.put(
                "/api/v1/user/preferences",
                json={
                    "voice_alerts_enabled": True,
                    "voice_volume": 0.85,
                    "voice_rate": 1.1,
                    "voice_pitch": 1.05,
                    "quiet_mode_enabled": False,
                    "selected_voice": "Google UK English Male"
                }
            )
            assert res_put.status_code == 200
            data = res_put.json()
            assert data["preferences"]["voice_pitch"] == 1.05

            # PUT invalid pitch (out of bounds)
            res_bad = client.put("/api/v1/user/preferences", json={"voice_pitch": 3.0})
            assert res_bad.status_code == 422

            # POST acknowledge alert
            res_ack = client.post("/api/v1/user/alerts/acknowledge", json={"intervention_id": "int-123"})
            assert res_ack.status_code == 200
            assert res_ack.json()["status"] == "success"
            assert res_ack.json()["intervention_id"] == "int-123"
        finally:
            app.dependency_overrides.pop(get_current_user, None)
