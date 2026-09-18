"""Backend tests for VisionGuard Mission 01."""
import sys
import os

# Ensure app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_application_imports_successfully():
    """Application should import successfully."""
    from app.main import app

    assert app is not None
    assert app.title is not None


def test_health_endpoint_returns_readiness():
    """/health should return READY status."""
    from app.main import app

    from fastapi.testclient import TestClient as TC

    client = TC(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "READY"


def test_system_status_returns_truthful_states():
    """/api/v1/system/status should return truthful states."""
    from app.main import app

    from fastapi.testclient import TestClient as TC

    client = TC(app)
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["camera"] == "NOT_CONFIGURED"
    assert data["ai_services"] == "NOT_CONFIGURED"
    assert data["state"] == "STOPPED"


class TestHumanStateModels:
    """Test core domain models validate correctly."""

    def _get_client(self):
        from app.main import app
        from fastapi.testclient import TestClient as TC
        return TC(app)

    def test_human_state_creation_with_minimal_data(self):
        """HumanState should create with minimal required fields."""
        from app.human_state.models import HumanState

        state = HumanState(track_id="visionguard-001")
        assert state.track_id == "visionguard-001"
        assert state.person_detected is False
        assert state.face_detected is False
        assert state.pose_detected is False
        assert state.risk_level is None
        assert state.risk_score is None

    def test_human_state_with_all_fields(self):
        """HumanState should accept all optional fields."""
        from app.human_state.models import HumanState

        state = HumanState(
            track_id="visionguard-001",
            person_detected=True,
            face_detected=True,
            pose_detected=True,
            posture_status="SLUMPED",
            posture_score=0.3,
            alertness_status="LOW",
            alertness_score=0.2,
            eye_state="CLOSED",
            eye_closure_duration=1.5,
            blink_rate=5.0,
            yawn_score=0.1,
            head_pitch=0.1,
            head_yaw=0.2,
            movement_score=0.4,
            risk_level="HIGH",
            risk_score=0.85,
            confidence=0.92,
        )
        assert state.track_id == "visionguard-001"
        assert state.person_detected is True
        assert state.posture_status == "SLUMPED"
        assert state.risk_level == "HIGH"
        assert state.risk_score == 0.85
        assert state.confidence == 0.92

    def test_human_state_create_minimal(self):
        """HumanStateCreate should work with minimal data."""
        from app.human_state.models import HumanStateCreate

        create = HumanStateCreate(track_id="visionguard-002")
        assert create.track_id == "visionguard-002"
        assert create.person_detected is False

    def test_human_state_create_with_data(self):
        """HumanStateCreate should accept provided values."""
        from app.human_state.models import HumanStateCreate

        create = HumanStateCreate(
            track_id="visionguard-002",
            person_detected=True,
            risk_level="LOW",
        )
        assert create.track_id == "visionguard-002"
        assert create.person_detected is True
        assert create.risk_level == "LOW"

    def test_human_state_is_alert_property(self):
        """is_alert should return True for HIGH/CRITICAL risk."""
        from app.human_state.models import HumanState

        high_state = HumanState(track_id="x", risk_level="HIGH")
        critical_state = HumanState(track_id="x", risk_level="CRITICAL")
        low_state = HumanState(track_id="x", risk_level="LOW")
        none_state = HumanState(track_id="x")

        assert high_state.is_alert is True
        assert critical_state.is_alert is True
        assert low_state.is_alert is False
        assert none_state.is_alert is False

    def test_human_state_is_safe_property(self):
        """is_safe should return True for LOW risk."""
        from app.human_state.models import HumanState

        low_state = HumanState(track_id="x", risk_level="LOW")
        high_state = HumanState(track_id="x", risk_level="HIGH")
        none_state = HumanState(track_id="x")

        assert low_state.is_safe is True
        assert high_state.is_safe is False
        assert none_state.is_safe is True


class TestCameraSource:
    """Test camera source protocol/contract."""

    def test_camera_source_methods_exist(self):
        """Camera source should have start/read/stop/health contract."""
        from app.camera.source import CameraSource

        import inspect

        # Verify the protocol has the required methods
        required_methods = ["start", "read", "stop", "health"]
        for method in required_methods:
            assert method in dir(CameraSource), f"Missing method: {method}"