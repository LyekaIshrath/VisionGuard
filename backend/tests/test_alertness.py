import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
"""Comprehensive Test Suite for Mission 04 Alertness Intelligence."""
import math
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.alertness.config import AlertnessConfig
from app.alertness.geometry import extract_face_geometry, FaceGeometry
from app.alertness.calibration import (
    AlertnessCalibrationService,
    CalibrationState,
    AlertnessBaseline,
)
from app.alertness.analyzer import (
    AlertnessAnalyzer,
    AlertnessStatus,
    AlertnessAnalysisResult,
)
from app.perception.engine import get_perception_engine


# --- Helpers for Synthetic Landmark Fixtures ---

def make_face_landmarks(
    left_ear_val: float = 0.30,
    right_ear_val: float = 0.30,
    mouth_mor_val: float = 0.20,
    head_pitch_val: float = 0.45,
    face_detected: bool = True,
) -> dict:
    """Construct synthetic landmark dictionary matching MediaPipeFace output."""
    if not face_detected:
        return {"face_detected": False, "eye_landmarks": {}, "mouth_landmarks": {}, "head_reference": {}}

    eye_w = 0.10
    left_v = eye_w * left_ear_val
    right_v = eye_w * right_ear_val
    mouth_w = 0.12
    mouth_v = mouth_w * mouth_mor_val

    return {
        "face_detected": True,
        "confidence": 0.95,
        "eye_landmarks": {
            "left_eye": {
                "outer": {"x": 0.30, "y": 0.40},
                "inner": {"x": 0.40, "y": 0.40},
                "top": {"x": 0.35, "y": 0.40 - left_v / 2.0},
                "bottom": {"x": 0.35, "y": 0.40 + left_v / 2.0},
            },
            "right_eye": {
                "outer": {"x": 0.60, "y": 0.40},
                "inner": {"x": 0.50, "y": 0.40},
                "top": {"x": 0.55, "y": 0.40 - right_v / 2.0},
                "bottom": {"x": 0.55, "y": 0.40 + right_v / 2.0},
            },
        },
        "mouth_landmarks": {
            "top": {"x": 0.45, "y": 0.65 - mouth_v / 2.0},
            "bottom": {"x": 0.45, "y": 0.65 + mouth_v / 2.0},
            "left": {"x": 0.39, "y": 0.65},
            "right": {"x": 0.51, "y": 0.65},
        },
        "head_reference": {
            "forehead": {"x": 0.45, "y": 0.20},
            "chin": {"x": 0.45, "y": 0.80},
            # chin.y - forehead.y = 0.60. Nose at forehead.y + 0.60 * head_pitch_val
            "nose_tip": {"x": 0.45, "y": 0.20 + 0.60 * head_pitch_val},
        },
    }


class TestAlertnessGeometry:
    """Deterministic tests for 2D facial geometry and EAR/MOR extraction."""

    def test_geometry_normal_eyes_and_mouth(self):
        data = make_face_landmarks(left_ear_val=0.32, right_ear_val=0.30, mouth_mor_val=0.22, head_pitch_val=0.48)
        geom = extract_face_geometry(data)
        assert geom.is_valid is True
        assert geom.left_eye_valid is True
        assert geom.right_eye_valid is True
        assert pytest.approx(geom.left_ear, 0.01) == 0.32
        assert pytest.approx(geom.right_ear, 0.01) == 0.30
        assert pytest.approx(geom.combined_ear, 0.01) == 0.31
        assert geom.confidence == 1.0
        assert geom.mouth_valid is True
        assert pytest.approx(geom.mouth_ratio, 0.01) == 0.22
        assert geom.head_valid is True
        assert pytest.approx(geom.head_pitch_ratio, 0.01) == 0.48

    def test_geometry_missing_landmarks_safety(self):
        geom_none = extract_face_geometry(None)
        assert geom_none.is_valid is False
        assert geom_none.combined_ear is None

        geom_no_face = extract_face_geometry({"face_detected": False})
        assert geom_no_face.is_valid is False
        assert geom_no_face.combined_ear is None

    def test_geometry_zero_width_and_nan_inf_protection(self):
        data = make_face_landmarks()
        # Set outer == inner (zero horizontal width)
        data["eye_landmarks"]["left_eye"]["outer"] = {"x": 0.35, "y": 0.40}
        data["eye_landmarks"]["left_eye"]["inner"] = {"x": 0.35, "y": 0.40}
        geom = extract_face_geometry(data)
        assert geom.left_eye_valid is False
        # Right eye still works
        assert geom.right_eye_valid is True
        assert geom.combined_ear == geom.right_ear
        assert geom.confidence == 0.65  # Single eye confidence

        # Inject NaN
        data["eye_landmarks"]["right_eye"]["outer"] = {"x": float("nan"), "y": 0.40}
        geom_nan = extract_face_geometry(data)
        assert geom_nan.left_eye_valid is False
        assert geom_nan.right_eye_valid is False
        assert geom_nan.combined_ear is None
        assert geom_nan.is_valid is False

    def test_geometry_single_eye_fusion_not_blind_min(self):
        """Verify when one eye is occluded/invalid, it does not falsely treat both as closed."""
        data = make_face_landmarks(left_ear_val=0.30, right_ear_val=0.30)
        # Invalidate left eye
        data["eye_landmarks"]["left_eye"]["top"] = None
        geom = extract_face_geometry(data)
        assert geom.left_eye_valid is False
        assert geom.right_eye_valid is True
        # Combined uses right eye, not min(0, right_ear)
        assert pytest.approx(geom.combined_ear, 0.01) == 0.30
        assert geom.confidence == 0.65


class TestAlertnessCalibration:
    """Tests for personal wakefulness baseline collection and threshold derivation."""

    def test_calibration_lifecycle_success(self):
        cal = AlertnessCalibrationService()
        cal.start_calibration()
        assert cal.state == CalibrationState.COLLECTING

        # Feed 40 consistent open-eye frames
        for _ in range(40):
            geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.32, right_ear_val=0.32, mouth_mor_val=0.20, head_pitch_val=0.45))
            cal.add_sample(geom)

        assert cal.state == CalibrationState.COMPLETED
        assert cal.is_calibrated is True
        baseline = cal.baseline
        assert baseline is not None
        assert pytest.approx(baseline.open_eye_ear, 0.01) == 0.32
        # Default closure threshold = 0.32 * 0.70 = 0.224
        assert pytest.approx(baseline.closed_eye_threshold, 0.01) == 0.224
        assert baseline.quality in ("EXCELLENT", "GOOD")

    def test_calibration_blink_outlier_filtering(self):
        """Verify normal blinks during calibration are filtered out and do NOT corrupt baseline."""
        cal = AlertnessCalibrationService()
        cal.start_calibration()

        # Feed 32 open frames (EAR ~0.32) and 8 closed/blink frames (EAR ~0.10)
        for _ in range(32):
            geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.32, right_ear_val=0.32))
            cal.add_sample(geom)
        for _ in range(8):
            geom_blink = extract_face_geometry(make_face_landmarks(left_ear_val=0.10, right_ear_val=0.10))
            cal.add_sample(geom_blink)

        assert cal.state == CalibrationState.COMPLETED
        baseline = cal.baseline
        assert baseline is not None
        # Baseline must match the true open eyes (~0.32), NOT the corrupted average
        assert pytest.approx(baseline.open_eye_ear, 0.02) == 0.32
        assert baseline.closed_eye_threshold > 0.20

    def test_calibration_unstable_samples_rejected(self):
        cal = AlertnessCalibrationService()
        cal.start_calibration()
        # Feed alternating extreme values that cause high CV
        for i in range(40):
            val = 0.15 if i % 2 == 0 else 0.45
            geom = extract_face_geometry(make_face_landmarks(left_ear_val=val, right_ear_val=val))
            cal.add_sample(geom)

        assert cal.state == CalibrationState.FAILED
        assert "unstable" in cal.get_status()["failure_reason"].lower()

    def test_calibration_reset_invalidates_baseline(self):
        cal = AlertnessCalibrationService()
        cal.start_calibration()
        for _ in range(40):
            cal.add_sample(extract_face_geometry(make_face_landmarks()))
        assert cal.is_calibrated is True

        cal.reset_calibration()
        assert cal.state == CalibrationState.IDLE
        assert cal.is_calibrated is False
        assert cal.baseline is None


class TestAlertnessTemporalSignals:
    """Tests for blink events, rate, PERCLOS proxy, yawns, and head drops."""

    @pytest.fixture
    def calibrated_analyzer(self):
        analyzer = AlertnessAnalyzer()
        baseline = AlertnessBaseline(
            open_eye_ear=0.30,
            closed_eye_threshold=0.21,
            mouth_mor=0.20,
            yawn_threshold=0.45,
            head_pitch_ratio=0.45,
            head_nod_threshold=0.55,
            samples_count=40,
            quality="EXCELLENT",
        )
        analyzer.set_baseline(baseline)
        return analyzer

    def test_single_blink_detection_no_double_counting(self, calibrated_analyzer):
        a = calibrated_analyzer
        t = 100.0

        # 1. Open eyes
        open_geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.30, right_ear_val=0.30))
        closed_geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.12, right_ear_val=0.12))

        a.analyze(open_geom, timestamp=t)
        assert len(a._blink_timestamps) == 0

        # 2. Closed for 0.15s (normal blink)
        a.analyze(closed_geom, timestamp=t + 0.10)
        assert len(a._blink_timestamps) == 0  # Not finished yet

        # 3. Eyes reopen -> blink counted!
        a.analyze(open_geom, timestamp=t + 0.18)
        assert len(a._blink_timestamps) == 1

        # 4. Continues open -> must NOT double count
        a.analyze(open_geom, timestamp=t + 0.25)
        assert len(a._blink_timestamps) == 1

    def test_long_closure_not_counted_as_blink(self, calibrated_analyzer):
        a = calibrated_analyzer
        t = 100.0
        open_geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.30, right_ear_val=0.30))
        closed_geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.12, right_ear_val=0.12))

        a.analyze(open_geom, timestamp=t)
        # Closed for 1.2s
        a.analyze(closed_geom, timestamp=t + 0.5)
        a.analyze(closed_geom, timestamp=t + 1.2)
        # Reopened
        a.analyze(open_geom, timestamp=t + 1.3)

        # Since closure duration was 1.2s > blink_max_duration_sec (0.40s), blink is NOT counted
        assert len(a._blink_timestamps) == 0

    def test_blink_rate_warmup_guard(self, calibrated_analyzer):
        a = calibrated_analyzer
        open_geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.30, right_ear_val=0.30))
        # Initial 5s of observation (< 15s required)
        res = a.analyze(open_geom, timestamp=105.0)
        assert res.blink_rate is None

    def test_perclos_proxy_elapsed_valid_time(self, calibrated_analyzer):
        a = calibrated_analyzer
        open_geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.30, right_ear_val=0.30))
        closed_geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.12, right_ear_val=0.12))

        # 8s open, 2s closed -> ~20% PERCLOS
        for i in range(8):
            a.analyze(open_geom, timestamp=100.0 + i)
        for i in range(2):
            a.analyze(closed_geom, timestamp=108.0 + i)

        res = a.analyze(closed_geom, timestamp=110.0)
        assert res.perclos_proxy is not None
        assert 0.15 <= res.perclos_proxy <= 0.35

    def test_face_missing_does_not_inflate_perclos(self, calibrated_analyzer):
        a = calibrated_analyzer
        open_geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.30, right_ear_val=0.30))
        # 10s open
        for i in range(10):
            a.analyze(open_geom, timestamp=100.0 + i)

        # Face disappears for 10s
        for i in range(10):
            res_missing = a.analyze(None, timestamp=110.0 + i)
            assert res_missing.status == AlertnessStatus.UNKNOWN

        # Face returns open
        res_return = a.analyze(open_geom, timestamp=121.0)
        # PERCLOS should still be 0.0 (closed time was 0), missing face did NOT count as closed
        assert res_return.perclos_proxy == 0.0

    def test_yawn_requires_temporal_duration(self, calibrated_analyzer):
        a = calibrated_analyzer
        normal_geom = extract_face_geometry(make_face_landmarks(mouth_mor_val=0.20))
        wide_mouth_geom = extract_face_geometry(make_face_landmarks(mouth_mor_val=0.60))

        # Brief opening (< 1.5s, e.g. talking/smiling)
        a.analyze(normal_geom, timestamp=100.0)
        a.analyze(wide_mouth_geom, timestamp=100.5)
        a.analyze(normal_geom, timestamp=101.0)
        assert len(a._yawn_timestamps) == 0

        # Sustained opening (>= 1.5s) -> yawn event
        a.analyze(wide_mouth_geom, timestamp=102.0)
        a.analyze(wide_mouth_geom, timestamp=103.8)
        assert len(a._yawn_timestamps) == 1

    def test_head_nod_requires_temporal_duration(self, calibrated_analyzer):
        a = calibrated_analyzer
        normal_geom = extract_face_geometry(make_face_landmarks(head_pitch_val=0.45))
        nod_geom = extract_face_geometry(make_face_landmarks(head_pitch_val=0.62))

        # Brief look down (0.3s)
        a.analyze(normal_geom, timestamp=100.0)
        res_brief = a.analyze(nod_geom, timestamp=100.3)
        assert res_brief.head_nod_signal is False

        # Sustained head nod (1.2s)
        res_sustained = a.analyze(nod_geom, timestamp=101.5)
        assert res_sustained.head_nod_signal is True


class TestTemporalDrowsinessAndHysteresis:
    """Tests for multi-signal fusion, alertness score bounds, and hysteresis."""

    @pytest.fixture
    def calibrated_analyzer(self):
        analyzer = AlertnessAnalyzer()
        baseline = AlertnessBaseline(
            open_eye_ear=0.30,
            closed_eye_threshold=0.21,
            mouth_mor=0.20,
            yawn_threshold=0.45,
            head_pitch_ratio=0.45,
            head_nod_threshold=0.55,
            samples_count=40,
            quality="EXCELLENT",
        )
        analyzer.set_baseline(baseline)
        return analyzer

    def test_normal_alert_maintains_high_score(self, calibrated_analyzer):
        a = calibrated_analyzer
        open_geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.30, right_ear_val=0.30))
        for i in range(10):
            res = a.analyze(open_geom, timestamp=100.0 + i * 0.1)
        assert res.status == AlertnessStatus.ALERT
        assert res.score is not None
        assert 95.0 <= res.score <= 100.0

    def test_sustained_eye_closure_triggers_possible_drowsiness(self, calibrated_analyzer):
        a = calibrated_analyzer
        open_geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.30, right_ear_val=0.30))
        closed_geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.10, right_ear_val=0.10))

        # Establish alert baseline
        a.analyze(open_geom, timestamp=100.0)

        # Eyes closed for 2.5 seconds
        for i in range(25):
            t = 100.0 + i * 0.1
            res = a.analyze(closed_geom, timestamp=t)

        # Evidence must be high and status transitioned to POSSIBLE_DROWSINESS
        assert res.evidence_score >= 0.55
        assert res.status == AlertnessStatus.POSSIBLE_DROWSINESS
        assert res.score is not None
        assert res.score <= 45.0

    def test_temporal_hysteresis_recovery_requires_sustained_open_eyes(self, calibrated_analyzer):
        a = calibrated_analyzer
        open_geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.30, right_ear_val=0.30))
        closed_geom = extract_face_geometry(make_face_landmarks(left_ear_val=0.10, right_ear_val=0.10))

        # 1. Drive into POSSIBLE_DROWSINESS
        for i in range(25):
            a.analyze(closed_geom, timestamp=100.0 + i * 0.1)
        assert a._current_status == AlertnessStatus.POSSIBLE_DROWSINESS

        # 2. Reopen eyes briefly (0.5s) -> must NOT immediately recover to ALERT (flicker protection)
        res_brief_open = a.analyze(open_geom, timestamp=103.0)
        assert res_brief_open.status == AlertnessStatus.POSSIBLE_DROWSINESS

        # 3. Reopen eyes for > 2.0s sustained -> recovers to ALERT
        for i in range(25):
            res_recovered = a.analyze(open_geom, timestamp=103.0 + i * 0.1)

        assert res_recovered.status == AlertnessStatus.ALERT


class TestAlertnessAPI:
    """Tests for /api/v1/alertness endpoints."""

    def test_alertness_calibration_api_lifecycle(self):
        client = TestClient(app)
        engine = get_perception_engine()
        engine.reset_alertness()

        # 1. Status initially IDLE
        res_status = client.get("/api/v1/alertness/calibration/status")
        assert res_status.status_code == 200
        assert res_status.json()["state"] == "IDLE"

        # 2. Start requires monitoring & face
        res_fail = client.post("/api/v1/alertness/calibration/start")
        # Should fail with 400 because monitoring is stopped or face not detected
        assert res_fail.status_code == 400

        # 3. Reset endpoint
        res_reset = client.post("/api/v1/alertness/calibration/reset")
        assert res_reset.status_code == 200
        assert res_reset.json()["status"] == "RESET"

    def test_websocket_stream_alertness_fields(self):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/monitoring/ws") as ws:
            ws.receive_json()  # status
            hs_msg = ws.receive_json()  # human_state
            assert hs_msg["type"] == "human_state"
            data = hs_msg["data"]
            assert "alertness_status" in data
            assert "alertness_score" in data
            assert "eye_state" in data
            assert "eye_closure_duration" in data
            assert "blink_rate" in data
            assert "yawn_score" in data
            assert "head_pitch" in data

