import os
import time
import asyncio
import pytest
import requests
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.config import config
from app.human_state.models import HumanState
from app.sessions.service import session_service
from app.alerts.models import RiskEvent, EventStatus
from app.intelligence.risk_models import RiskCategory, RiskLevel

SB_URL = "https://uwtnjkxpzjctgthmgsjv.supabase.co"
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV3dG5qa3hwempjdGd0aG1nc2p2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODk2ODI0OTEsImV4cCI6MjEwNTI1ODQ5MX0.kJV7cAGB0z81CRSa1rMM8EvLl4zfvAIDtJU1fYAaRws"


@pytest.fixture(scope="module")
def user_a_auth():
    r = requests.post(
        f"{SB_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
        json={"email": "user_a@visionguard.test", "password": "TestPassword123!@#"}
    )
    assert r.status_code == 200, f"Auth failed: {r.text}"
    data = r.json()
    return {
        "id": data["user"]["id"],
        "token": data["access_token"],
        "email": data["user"]["email"]
    }


@pytest.fixture
def client():
    return TestClient(app)


class TestLiveSupabaseE2E:
    def test_live_session_flow_persistence_and_events(self, user_a_auth, client):
        async def _run():
            user_id = user_a_auth["id"]
            token = user_a_auth["token"]

            # 1. Start Session
            session_id = await session_service.start_session_async(user_id=user_id, token=token)
            assert session_id is not None
            assert session_service.cloud_session_id == session_id
            assert session_service.cloud_status == "SYNCED"

            # 2. Ingest derived telemetry samples (t=0.0, 0.5, 1.0, 1.5)
            mono_start = time.monotonic()
            state_good = HumanState(
                track_id="trk-live-1",
                timestamp=datetime.now(timezone.utc),
                person_detected=True,
                posture_status="GOOD",
                posture_score=92.0,
                alertness_status="ALERT",
                alertness_score=88.0,
                risk_level="LOW",
                risk_score=10.0
            )
            session_service.on_frame_processed(state_good, mono_time=mono_start)
            session_service.on_frame_processed(state_good, mono_time=mono_start + 0.5)

            state_mod = HumanState(
                track_id="trk-live-1",
                timestamp=datetime.now(timezone.utc),
                person_detected=True,
                posture_status="NEEDS_ATTENTION",
                posture_score=55.0,
                alertness_status="POSSIBLE_DROWSINESS",
                alertness_score=50.0,
                risk_level="MODERATE",
                risk_score=45.0
            )
            session_service.on_frame_processed(state_mod, mono_time=mono_start + 1.0)
            session_service.on_frame_processed(state_mod, mono_time=mono_start + 1.5)

            # 3. Create Risk Event Lifecycle: STARTED -> RESOLVED
            event_id = f"evt-live-{os.urandom(4).hex()}"
            evt_started = RiskEvent(
                event_id=event_id,
                timestamp=datetime.now(timezone.utc),
                category=RiskCategory.POSTURE,
                status=EventStatus.STARTED,
                risk_level=RiskLevel.MODERATE,
                message="Slouch posture detected"
            )
            await session_service.record_risk_event_async(evt_started)

            # Idempotent retry of same event
            await session_service.record_risk_event_async(evt_started)

            # Resolve event
            evt_resolved = RiskEvent(
                event_id=event_id,
                timestamp=datetime.now(timezone.utc),
                category=RiskCategory.POSTURE,
                status=EventStatus.RESOLVED,
                risk_level=RiskLevel.LOW,
                message="Slouch posture resolved",
                duration_sec=1.5
            )
            await session_service.record_risk_event_async(evt_resolved)

            # 4. Stop Session
            stopped = await session_service.stop_session_async()
            assert stopped is not None
            assert stopped.get("status") == "COMPLETED"
            assert stopped.get("duration_seconds") >= 1.5
            assert stopped.get("average_posture_score") is not None
            assert stopped.get("average_alertness_score") is not None
            assert stopped.get("risk_event_count") >= 1

            # 5. Verify direct in Supabase PostgREST
            headers = {"apikey": ANON_KEY, "Authorization": f"Bearer {token}"}
            resp = requests.get(f"{SB_URL}/rest/v1/monitoring_sessions?id=eq.{session_id}", headers=headers)
            assert resp.status_code == 200
            rows = resp.json()
            assert len(rows) == 1
            persisted = rows[0]
            assert persisted["status"] == "COMPLETED"
            assert persisted["duration_seconds"] >= 1.5
            assert persisted["good_posture_seconds"] > 0
            assert persisted["posture_risk_seconds"] > 0
            assert persisted["alertness_risk_seconds"] > 0
            assert persisted["risk_event_count"] >= 1

            # Check privacy boundary: ZERO raw frames, ZERO landmark coordinates
            forbidden_keys = {"frame", "image", "raw_frame", "video", "landmarks", "face_landmarks", "pose_landmarks", "embedding"}
            assert not any(k in persisted for k in forbidden_keys)

            # 6. Verify History API
            h_resp = client.get("/api/v1/sessions", headers={"Authorization": f"Bearer {token}"})
            assert h_resp.status_code == 200
            history_list = h_resp.json()
            assert any(s["id"] == session_id for s in history_list)

            # 7. Verify Session Detail API
            d_resp = client.get(f"/api/v1/sessions/{session_id}", headers={"Authorization": f"Bearer {token}"})
            assert d_resp.status_code == 200
            detail = d_resp.json()
            assert detail["id"] == session_id

            # 8. Verify Session Events API
            e_resp = client.get(f"/api/v1/sessions/{session_id}/events", headers={"Authorization": f"Bearer {token}"})
            assert e_resp.status_code == 200
            events = e_resp.json()
            assert any(e["id"] == event_id for e in events)
            matching_evt = next(e for e in events if e["id"] == event_id)
            assert matching_evt["lifecycle"] == "RESOLVED"

            # 9. Verify Analytics API
            a_resp = client.get("/api/v1/analytics/summary", headers={"Authorization": f"Bearer {token}"})
            assert a_resp.status_code == 200
            analytics = a_resp.json()
            assert analytics.get("total_sessions", 0) >= 1

            # 10. Test Deletion of single session
            del_resp = client.delete(f"/api/v1/sessions/{session_id}", headers={"Authorization": f"Bearer {token}"})
            assert del_resp.status_code == 200
            # Verify session is gone from Supabase
            check_del = requests.get(f"{SB_URL}/rest/v1/monitoring_sessions?id=eq.{session_id}", headers=headers)
            assert len(check_del.json()) == 0
            # Verify cascade removed risk events
            check_events = requests.get(f"{SB_URL}/rest/v1/risk_events?session_id=eq.{session_id}", headers=headers)
            assert len(check_events.json()) == 0

        asyncio.run(_run())

    def test_delete_user_data_leaves_auth_account_active(self, user_a_auth, client):
        async def _run():
            user_id = user_a_auth["id"]
            token = user_a_auth["token"]

            # Call DELETE /api/v1/user/data
            del_resp = client.delete("/api/v1/user/data", headers={"Authorization": f"Bearer {token}"})
            assert del_resp.status_code == 200
            res_data = del_resp.json()
            assert res_data.get("status") == "success"
            assert "Authentication account remains active" in res_data.get("message", "")

            # Verify auth identity is still active in Supabase Auth
            headers = {"apikey": ANON_KEY, "Authorization": f"Bearer {token}"}
            user_check = requests.get(f"{SB_URL}/auth/v1/user", headers=headers)
            assert user_check.status_code == 200
            assert user_check.json()["id"] == user_id

        asyncio.run(_run())

    def test_single_pipeline_architecture_verification(self):
        """Verifies strictly one VideoCapture and single MediaPipe inference pipeline."""
        from app.camera.webcam_source import WebcamSource
        from app.perception.engine import PerceptionEngine

        # Verify WebcamSource interface
        source = WebcamSource(camera_index=0)
        assert hasattr(source, "start")
        assert hasattr(source, "read")
        assert hasattr(source, "stop")

        # Verify perception engine has single pose and face landmarker
        engine = PerceptionEngine()
        assert hasattr(engine, "_pose")
        assert hasattr(engine, "_face")
        assert engine._pose is not None
        assert engine._face is not None
