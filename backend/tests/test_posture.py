"""Deterministic Synthetic Algorithm Tests for VisionGuard Mission 03.

DISCLAIMER:
These are synthetic algorithm tests using simulated 2D landmark coordinates.
They validate mathematical normalization, geometric proxies, temporal reasoning,
posture scoring, calibration lifecycle, and API contracts.
THEY DO NOT CONSTITUTE PHYSICAL WEBCAM VALIDATION.
"""

import sys
import os
import math
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

# Ensure app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app
from app.posture.geometry import extract_body_geometry, BodyGeometry, Point2D
from app.posture.calibration import (
    PostureCalibrationService,
    PostureBaseline,
    CalibrationState,
)
from app.posture.analyzer import (
    PostureAnalyzer,
    PostureStatus,
    PostureResult,
)
from app.human_state.models import HumanState
from app.perception.engine import get_perception_engine
from app.camera.manager import get_camera_manager


# --- Helper: Synthetic Landmark Generators ---

def make_synthetic_landmarks(
    head_y: float = 0.20,
    head_x: float = 0.50,
    l_shoulder_x: float = 0.60,
    l_shoulder_y: float = 0.40,
    r_shoulder_x: float = 0.40,
    r_shoulder_y: float = 0.40,
    l_hip_x: float = 0.58,
    l_hip_y: float = 0.70,
    r_hip_x: float = 0.42,
    r_hip_y: float = 0.70,
    confidence: float = 0.95,
):
    """Generate synthetic MediaPipe-style landmarks for testing.

    Anatomical conventions:
    - left_shoulder: anatomical left (viewer's right, x=0.60)
    - right_shoulder: anatomical right (viewer's left, x=0.40)
    """
    return {
        "nose": {"x": head_x, "y": head_y, "z": 0.0, "visibility": confidence},
        "left_ear": {"x": head_x + 0.03, "y": head_y - 0.02, "z": 0.0, "visibility": confidence},
        "right_ear": {"x": head_x - 0.03, "y": head_y - 0.02, "z": 0.0, "visibility": confidence},
        "left_shoulder": {"x": l_shoulder_x, "y": l_shoulder_y, "z": 0.0, "visibility": confidence},
        "right_shoulder": {"x": r_shoulder_x, "y": r_shoulder_y, "z": 0.0, "visibility": confidence},
        "left_hip": {"x": l_hip_x, "y": l_hip_y, "z": 0.0, "visibility": confidence},
        "right_hip": {"x": r_hip_x, "y": r_hip_y, "z": 0.0, "visibility": confidence},
    }


@pytest.fixture
def calibrated_analyzer():
    upright = extract_body_geometry(make_synthetic_landmarks())
    assert upright is not None
    baseline = PostureBaseline(
        shoulder_width=upright.shoulder_width,
        torso_length=upright.torso_length,
        shoulder_tilt=upright.shoulder_tilt,
        head_lateral_displacement=upright.head_lateral_displacement,
        torso_lateral_displacement=upright.torso_lateral_displacement,
        head_shoulder_vertical_ratio=upright.head_shoulder_vertical_ratio,
        slouch_proxy=upright.slouch_proxy,
        forward_lean_proxy=upright.forward_lean_proxy,
        confidence=upright.confidence,
        quality="EXCELLENT",
        sample_count=40,
    )
    return PostureAnalyzer(baseline=baseline)


# ============================================================================
# Section A: Geometry Tests
# ============================================================================

class TestBodyGeometry:
    """Synthetic algorithm tests for BodyGeometry extraction and normalization."""

    def test_geometry_normal_upright(self):
        landmarks = make_synthetic_landmarks()
        geo = extract_body_geometry(landmarks)
        assert geo is not None
        assert math.isclose(geo.shoulder_width, 0.20, abs_tol=1e-3)
        assert geo.shoulder_midpoint == (0.50, 0.40)
        assert geo.hip_midpoint == (0.50, 0.70)
        assert math.isclose(geo.torso_length, 0.30, abs_tol=1e-3)
        assert math.isclose(geo.shoulder_tilt, 0.0, abs_tol=1e-3)
        assert math.isclose(geo.head_lateral_displacement, 0.0, abs_tol=1e-3)
        assert geo.slouch_proxy > 0.9  # Head is well above shoulders

    def test_geometry_zero_division_protection(self):
        # Shoulders coincident (shoulder_width = 0)
        landmarks = make_synthetic_landmarks(
            l_shoulder_x=0.50, r_shoulder_x=0.50,
            l_shoulder_y=0.40, r_shoulder_y=0.40,
        )
        geo = extract_body_geometry(landmarks)
        assert geo is None, "Coincident shoulders must return None rather than divide by zero"

    def test_geometry_missing_required_landmarks(self):
        landmarks = make_synthetic_landmarks()
        del landmarks["left_shoulder"]
        assert extract_body_geometry(landmarks) is None

        landmarks = make_synthetic_landmarks()
        landmarks["nose"] = None
        assert extract_body_geometry(landmarks) is None

    def test_geometry_nan_inf_protection(self):
        landmarks = make_synthetic_landmarks()
        landmarks["left_shoulder"]["x"] = float("nan")
        assert extract_body_geometry(landmarks) is None

        landmarks = make_synthetic_landmarks()
        landmarks["right_shoulder"]["y"] = float("inf")
        assert extract_body_geometry(landmarks) is None

    def test_geometry_low_confidence_rejection(self):
        landmarks = make_synthetic_landmarks(confidence=0.3)
        geo = extract_body_geometry(landmarks, min_confidence=0.5)
        assert geo is None

    def test_geometry_slouch_proxy_decreases_when_slouched(self):
        upright_lm = make_synthetic_landmarks(head_y=0.20)
        slouched_lm = make_synthetic_landmarks(head_y=0.35)  # Head dropped towards shoulders (y=0.40)

        geo_upright = extract_body_geometry(upright_lm)
        geo_slouched = extract_body_geometry(slouched_lm)

        assert geo_upright is not None and geo_slouched is not None
        assert geo_slouched.slouch_proxy < geo_upright.slouch_proxy, "Slouching must decrease slouch_proxy"

    def test_geometry_forward_lean_proxy_increases(self):
        upright_lm = make_synthetic_landmarks(
            l_shoulder_x=0.60, r_shoulder_x=0.40,
        )
        forward_lm = make_synthetic_landmarks(
            l_shoulder_x=0.65, r_shoulder_x=0.35,
        )
        geo_upright = extract_body_geometry(upright_lm)
        geo_forward = extract_body_geometry(forward_lm)

        assert geo_upright is not None and geo_forward is not None
        assert geo_forward.forward_lean_proxy > geo_upright.forward_lean_proxy

    def test_geometry_anatomical_left_vs_right_lean(self):
        # Anatomical Left: head shifts towards left shoulder (x > 0.50 in unmirrored frame)
        left_lm = make_synthetic_landmarks(head_x=0.56)
        geo_left = extract_body_geometry(left_lm)
        assert geo_left is not None
        assert geo_left.head_lateral_displacement > 0.20, "Displacement towards anatomical left must be positive"

        # Anatomical Right: head shifts towards right shoulder (x < 0.50 in unmirrored frame)
        right_lm = make_synthetic_landmarks(head_x=0.44)
        geo_right = extract_body_geometry(right_lm)
        assert geo_right is not None
        assert geo_right.head_lateral_displacement < -0.20, "Displacement towards anatomical right must be negative"


# ============================================================================
# Section B: Calibration Tests
# ============================================================================

class TestPostureCalibration:
    """Synthetic algorithm tests for PostureCalibrationService."""

    def test_calibration_success_with_stable_samples(self):
        service = PostureCalibrationService(required_samples=10)
        service.start_calibration()
        assert service.state == CalibrationState.COLLECTING

        base_lm = make_synthetic_landmarks()
        geo = extract_body_geometry(base_lm)

        for i in range(10):
            state = service.add_sample(geo)

        assert state == CalibrationState.COMPLETED
        assert service.is_calibrated is True
        assert service.baseline is not None
        assert service.baseline.sample_count == 10
        assert service.baseline.quality in ("EXCELLENT", "GOOD", "ACCEPTABLE")

    def test_calibration_insufficient_samples_does_not_complete(self):
        service = PostureCalibrationService(required_samples=10)
        service.start_calibration()

        geo = extract_body_geometry(make_synthetic_landmarks())
        for _ in range(5):
            service.add_sample(geo)

        assert service.state == CalibrationState.COLLECTING
        assert service.is_calibrated is False
        status = service.get_status()
        assert status["valid_samples"] == 5
        assert status["progress"] == 0.5

    def test_calibration_unstable_samples_rejected(self):
        service = PostureCalibrationService(required_samples=10)
        service.start_calibration()

        # Alternate wildly between upright and heavily tilted/moved samples
        for i in range(10):
            if i % 2 == 0:
                geo = extract_body_geometry(make_synthetic_landmarks(head_x=0.50, l_shoulder_y=0.40))
            else:
                geo = extract_body_geometry(make_synthetic_landmarks(head_x=0.70, l_shoulder_y=0.55))
            service.add_sample(geo)

        assert service.state == CalibrationState.FAILED
        status = service.get_status()
        assert "EXCESSIVE_MOVEMENT" in status["failure_reason"]
        assert service.baseline is None

    def test_calibration_reset_invalidates_baseline(self):
        service = PostureCalibrationService(required_samples=5)
        service.start_calibration()
        geo = extract_body_geometry(make_synthetic_landmarks())
        for _ in range(5):
            service.add_sample(geo)

        assert service.is_calibrated is True
        service.reset_calibration()
        assert service.state == CalibrationState.IDLE
        assert service.is_calibrated is False
        assert service.baseline is None
        assert service.get_status()["valid_samples"] == 0

    def test_baseline_immutability(self):
        service = PostureCalibrationService(required_samples=5)
        service.start_calibration()
        geo = extract_body_geometry(make_synthetic_landmarks())
        for _ in range(5):
            service.add_sample(geo)

        b1 = service.baseline
        assert b1 is not None

        # Subsequent sample addition when completed should not mutate baseline
        service.add_sample(extract_body_geometry(make_synthetic_landmarks(head_y=0.35)))
        assert service.baseline == b1


# ============================================================================
# Section C: Analyzer Tests
# ============================================================================

class TestPostureAnalyzer:
    """Synthetic algorithm tests for PostureAnalyzer (classification, scoring, temporal logic)."""

    def test_analyzer_uncalibrated(self):
        analyzer = PostureAnalyzer(baseline=None)
        res = analyzer.analyze(extract_body_geometry(make_synthetic_landmarks()))
        assert res.instantaneous_status == PostureStatus.NOT_CALIBRATED
        assert res.stable_status == PostureStatus.NOT_CALIBRATED
        assert res.instantaneous_score is None
        assert res.smoothed_score is None

    def test_analyzer_good_near_baseline(self, calibrated_analyzer):
        geo = extract_body_geometry(make_synthetic_landmarks())
        res = calibrated_analyzer.analyze(geo, timestamp=100.0)
        assert res.instantaneous_status == PostureStatus.GOOD
        assert res.stable_status == PostureStatus.GOOD
        assert res.instantaneous_score is not None and res.instantaneous_score >= 95.0

    def test_analyzer_score_bounds_and_monotonicity(self, calibrated_analyzer):
        # 1. Baseline
        r0 = calibrated_analyzer.analyze(extract_body_geometry(make_synthetic_landmarks(head_y=0.20)), timestamp=100.0)
        # 2. Mild slouch (head drops slightly)
        r1 = calibrated_analyzer.analyze(extract_body_geometry(make_synthetic_landmarks(head_y=0.25)), timestamp=101.0)
        # 3. Moderate slouch
        r2 = calibrated_analyzer.analyze(extract_body_geometry(make_synthetic_landmarks(head_y=0.32)), timestamp=102.0)
        # 4. Severe slouch
        r3 = calibrated_analyzer.analyze(extract_body_geometry(make_synthetic_landmarks(head_y=0.38)), timestamp=103.0)

        # Monotonicity check on instantaneous scores
        assert r0.instantaneous_score > r1.instantaneous_score
        assert r1.instantaneous_score > r2.instantaneous_score
        assert r2.instantaneous_score > r3.instantaneous_score

        # Bound check [0, 100]
        for r in (r0, r1, r2, r3):
            assert 0.0 <= r.instantaneous_score <= 100.0
            assert 0.0 <= r.smoothed_score <= 100.0

    def test_analyzer_detects_slouching(self, calibrated_analyzer):
        slouched = extract_body_geometry(make_synthetic_landmarks(head_y=0.35))
        res = calibrated_analyzer.analyze(slouched, timestamp=100.0)
        assert res.instantaneous_status == PostureStatus.SLOUCHING

    def test_analyzer_detects_forward_lean(self, calibrated_analyzer):
        # Shoulders expand by 40% (lean into camera)
        fwd = extract_body_geometry(make_synthetic_landmarks(l_shoulder_x=0.64, r_shoulder_x=0.36))
        res = calibrated_analyzer.analyze(fwd, timestamp=100.0)
        assert res.instantaneous_status == PostureStatus.FORWARD_LEAN

    def test_analyzer_detects_left_and_right_lean(self, calibrated_analyzer):
        # Anatomical Left lean
        left_geo = extract_body_geometry(make_synthetic_landmarks(head_x=0.55))
        r_left = calibrated_analyzer.analyze(left_geo, timestamp=100.0)
        assert r_left.instantaneous_status == PostureStatus.LEFT_LEAN

        # Anatomical Right lean
        right_geo = extract_body_geometry(make_synthetic_landmarks(head_x=0.45))
        r_right = calibrated_analyzer.analyze(right_geo, timestamp=100.0)
        assert r_right.instantaneous_status == PostureStatus.RIGHT_LEAN

    def test_temporal_transient_disturbance_rejected(self, calibrated_analyzer):
        # Frame at t=100.0 (upright)
        calibrated_analyzer.analyze(extract_body_geometry(make_synthetic_landmarks(head_y=0.20)), timestamp=100.0)
        assert calibrated_analyzer._stable_status == PostureStatus.GOOD

        # Brief ~0.5s disturbance: picking up pen / sudden glitch at t=100.5
        calibrated_analyzer.analyze(extract_body_geometry(make_synthetic_landmarks(head_y=0.35)), timestamp=100.2)
        r_brief = calibrated_analyzer.analyze(extract_body_geometry(make_synthetic_landmarks(head_y=0.35)), timestamp=100.5)

        # Instantaneous detected slouch, but stable state remains GOOD!
        assert r_brief.instantaneous_status == PostureStatus.SLOUCHING
        assert r_brief.stable_status == PostureStatus.GOOD, "0.5s disturbance must NOT change stable state"

        # User sits back upright at t=100.8
        r_back = calibrated_analyzer.analyze(extract_body_geometry(make_synthetic_landmarks(head_y=0.20)), timestamp=100.8)
        assert r_back.instantaneous_status == PostureStatus.GOOD
        assert r_back.stable_status == PostureStatus.GOOD

    def test_temporal_sustained_deviation_accepted(self, calibrated_analyzer):
        # Upright at t=100.0
        calibrated_analyzer.analyze(extract_body_geometry(make_synthetic_landmarks(head_y=0.20)), timestamp=100.0)

        # Slouch begins at t=101.0
        calibrated_analyzer.analyze(extract_body_geometry(make_synthetic_landmarks(head_y=0.36)), timestamp=101.0)
        # Continues at t=102.0 (1.0s elapsed - not yet reached 1.5s)
        r_mid = calibrated_analyzer.analyze(extract_body_geometry(make_synthetic_landmarks(head_y=0.36)), timestamp=102.0)
        assert r_mid.stable_status == PostureStatus.GOOD

        # Sustained to t=102.6 (1.6s elapsed > 1.5s threshold)
        r_sustained = calibrated_analyzer.analyze(extract_body_geometry(make_synthetic_landmarks(head_y=0.36)), timestamp=102.6)
        assert r_sustained.stable_status == PostureStatus.SLOUCHING, "1.6s sustained deviation MUST transition stable state"

    def test_confidence_and_score_independence(self, calibrated_analyzer):
        # 1. High confidence detection with severe slouch (large deviation)
        severe_slouch = extract_body_geometry(make_synthetic_landmarks(head_y=0.36, confidence=0.98))
        res = calibrated_analyzer.analyze(severe_slouch, timestamp=100.0)
        assert res.confidence >= 0.95, "Confidence should reflect high detection certainty"
        assert res.instantaneous_score is not None and res.instantaneous_score < 50.0, "Score should reflect large posture deviation"

        # 2. Moderate slouch with lower but acceptable confidence (0.55)
        mod_slouch = extract_body_geometry(make_synthetic_landmarks(head_y=0.28, confidence=0.55), min_confidence=0.5)
        res_mod = calibrated_analyzer.analyze(mod_slouch, timestamp=101.0)
        assert res_mod.confidence < 0.60
        # Posture score depends on geometry, not confidence
        assert res_mod.instantaneous_score is not None and res_mod.instantaneous_score > res.instantaneous_score


# ============================================================================
# Section D: API Lifecycle & Integration Tests
# ============================================================================

class TestPostureAPI:
    """Integration and contract tests for Posture API endpoints."""

    def test_calibration_api_lifecycle(self):
        client = TestClient(app)

        # 1. Reset posture
        res_reset = client.post("/api/v1/posture/calibration/reset")
        assert res_reset.status_code == 200
        assert res_reset.json() == {"status": "RESET", "state": "IDLE"}

        # 2. Check status is IDLE
        res_status = client.get("/api/v1/posture/calibration/status")
        assert res_status.status_code == 200
        data = res_status.json()
        assert data["state"] == "IDLE"
        assert data["valid_samples"] == 0
        assert data["progress"] == 0.0

        # 3. Attempt start without monitoring/pose (should fail cleanly with 400)
        res_start_fail = client.post("/api/v1/posture/calibration/start")
        assert res_start_fail.status_code == 400
        assert "Monitoring must be running" in res_start_fail.json()["detail"] or "Person and pose must be detected" in res_start_fail.json()["detail"]

    def test_human_state_posture_fields_integration(self):
        engine = get_perception_engine()
        engine.reset_posture()

        # Before calibration:
        state_uncal = engine.process_frame(None)
        assert state_uncal.posture_status == "NOT_CALIBRATED"
        assert state_uncal.posture_score is None
        # Mission 04+ fields must remain untouched
        assert state_uncal.alertness_status is None
        assert state_uncal.alertness_score is None
        assert state_uncal.risk_score is None

        # Manually seed a completed calibration for testing
        upright = extract_body_geometry(make_synthetic_landmarks())
        assert upright is not None
        baseline = PostureBaseline(
            shoulder_width=upright.shoulder_width,
            torso_length=upright.torso_length,
            shoulder_tilt=upright.shoulder_tilt,
            head_lateral_displacement=upright.head_lateral_displacement,
            torso_lateral_displacement=upright.torso_lateral_displacement,
            head_shoulder_vertical_ratio=upright.head_shoulder_vertical_ratio,
            slouch_proxy=upright.slouch_proxy,
            forward_lean_proxy=upright.forward_lean_proxy,
            confidence=0.95,
            quality="EXCELLENT",
            sample_count=40,
        )
        engine.calibration_service._baseline = baseline
        engine.calibration_service._state = CalibrationState.COMPLETED
        engine.posture_analyzer.set_baseline(baseline)

        # After calibration, with valid geometry:
        res = engine.posture_analyzer.analyze(upright, timestamp=100.0)
        assert res.stable_status == PostureStatus.GOOD
        assert res.smoothed_score is not None
        assert 90.0 <= res.smoothed_score <= 100.0

        # Clean up
        engine.reset_posture()

    def test_websocket_stream_schema(self):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/monitoring/ws") as ws:
            # 1. Initial status message
            init_msg = ws.receive_json()
            assert init_msg["type"] == "status"
            assert "state" in init_msg["data"]

            # 2. Real-time human_state stream message
            hs_msg = ws.receive_json()
            assert hs_msg["type"] == "human_state"
            data = hs_msg["data"]
            assert "track_id" in data
            assert "person_detected" in data
            assert "face_detected" in data
            assert "pose_detected" in data
            assert "posture_status" in data
            assert "posture_score" in data
            assert "confidence" in data
            # Ensure no huge raw landmark arrays or video frames transmitted
            assert "landmarks" not in data
            assert "frame" not in data
            assert "image" not in data
