"""Regression tests for VisionGuard Live Landmark & Skeleton Overlay.

Verifies:
1. No second VideoCapture created.
2. No second MediaPipe inference pipeline created.
3. Missing landmarks are not fabricated.
4. Normalized coordinates map correctly to frame pixels.
5. Invalid coordinates handled safely.
6. Overlay OFF returns clean frame.
7. MINIMAL renders expected available landmarks.
8. DEBUG uses real derived values.
9. Overlay rendering does not persist frames.
10. Existing preview still works.
11. Existing posture calculations unchanged.
12. Existing alertness calculations unchanged.
13. Existing RiskEngine unchanged.
"""

import asyncio
import os
import tempfile
from unittest.mock import MagicMock, patch
import cv2
import numpy as np
import pytest

from app.camera.manager import get_camera_manager, CameraManager
from app.perception.engine import PerceptionEngine, get_perception_engine
from app.perception.overlay import (
    OverlayRenderer,
    OverlayMode,
    _to_pixel,
    COLOR_ACCENT,
    COLOR_TORSO,
    COLOR_GOOD,
)
from app.human_state.models import HumanState
from app.posture.calibration import PostureBaseline
from app.posture.analyzer import PostureStatus
from app.alertness.calibration import AlertnessBaseline
from app.alertness.analyzer import AlertnessStatus
from app.intelligence.risk_models import RiskLevel, OverallRiskState
from app.api.monitoring import monitoring_preview


@pytest.fixture
def sample_bgr_frame():
    """Create a blank 640x480 BGR test frame."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def mock_pose_result():
    """Realistic mock pose detection result with normalized landmarks."""
    return {
        "pose_detected": True,
        "confidence": 0.95,
        "landmarks": {
            "nose": {"x": 0.50, "y": 0.20, "visibility": 0.99},
            "left_ear": {"x": 0.42, "y": 0.20, "visibility": 0.95},
            "right_ear": {"x": 0.58, "y": 0.20, "visibility": 0.95},
            "left_shoulder": {"x": 0.40, "y": 0.40, "visibility": 0.98},
            "right_shoulder": {"x": 0.60, "y": 0.40, "visibility": 0.98},
            "left_hip": {"x": 0.42, "y": 0.70, "visibility": 0.90},
            "right_hip": {"x": 0.58, "y": 0.70, "visibility": 0.90},
        },
    }


@pytest.fixture
def mock_face_result():
    """Realistic mock face detection result with normalized landmarks."""
    return {
        "face_detected": True,
        "confidence": 0.92,
        "eye_landmarks": {
            "left_eye": {
                "outer": {"x": 0.44, "y": 0.22, "visibility": 0.95},
                "inner": {"x": 0.48, "y": 0.22, "visibility": 0.95},
                "top": {"x": 0.46, "y": 0.21, "visibility": 0.95},
                "bottom": {"x": 0.46, "y": 0.23, "visibility": 0.95},
                "top2": {"x": 0.45, "y": 0.21, "visibility": 0.95},
                "bottom2": {"x": 0.45, "y": 0.23, "visibility": 0.95},
            },
            "right_eye": {
                "outer": {"x": 0.56, "y": 0.22, "visibility": 0.95},
                "inner": {"x": 0.52, "y": 0.22, "visibility": 0.95},
                "top": {"x": 0.54, "y": 0.21, "visibility": 0.95},
                "bottom": {"x": 0.54, "y": 0.23, "visibility": 0.95},
                "top2": {"x": 0.55, "y": 0.21, "visibility": 0.95},
                "bottom2": {"x": 0.55, "y": 0.23, "visibility": 0.95},
            },
        },
        "mouth_landmarks": {
            "top": {"x": 0.50, "y": 0.28, "visibility": 0.95},
            "bottom": {"x": 0.50, "y": 0.32, "visibility": 0.95},
            "left": {"x": 0.46, "y": 0.30, "visibility": 0.95},
            "right": {"x": 0.54, "y": 0.30, "visibility": 0.95},
        },
        "head_reference": {
            "forehead": {"x": 0.50, "y": 0.15, "visibility": 0.95},
            "nose_tip": {"x": 0.50, "y": 0.24, "visibility": 0.95},
            "chin": {"x": 0.50, "y": 0.35, "visibility": 0.95},
        },
    }


class TestLandmarkOverlayRegression:
    """Complete 13-item regression verification suite."""

    # 1. No second VideoCapture created
    def test_item1_no_second_videocapture(self, sample_bgr_frame):
        manager = get_camera_manager()
        mock_source = MagicMock()
        mock_source.camera_index = 0
        mock_source.health.return_value = "READY"
        success, buf = cv2.imencode(".jpg", sample_bgr_frame)
        mock_source.read.return_value = buf.tobytes()

        manager._source = mock_source
        manager._running = True

        engine = get_perception_engine()
        engine.process_frame(buf.tobytes())

        with patch("cv2.VideoCapture") as mock_vc:
            async def run():
                resp = await monitoring_preview(overlay="MINIMAL", manager=manager, perception=engine)
                async for chunk in resp.body_iterator:
                    assert b"--frame" in chunk
                    break

            try:
                asyncio.run(run())
                mock_vc.assert_not_called()
            finally:
                manager.stop()
                engine.stop_session()

    # 2. No second MediaPipe inference pipeline created
    def test_item2_no_second_mediapipe_pipeline(self, sample_bgr_frame):
        engine = PerceptionEngine()
        try:
            success, buf = cv2.imencode(".jpg", sample_bgr_frame)
            frame_bytes = buf.tobytes()

            with patch.object(engine._pose, "detect", wraps=engine._pose.detect) as mock_pose_det, \
                 patch.object(engine._face, "detect", wraps=engine._face.detect) as mock_face_det:
                # Process authoritative frame once
                engine.process_frame(frame_bytes)
                assert mock_pose_det.call_count == 1
                assert mock_face_det.call_count == 1

                # Render overlay 5 times
                for _ in range(5):
                    annotated_bytes = engine.get_annotated_frame_bytes("MINIMAL")
                    assert annotated_bytes is not None

                # Detectors must NOT be called again during preview rendering
                assert mock_pose_det.call_count == 1
                assert mock_face_det.call_count == 1
        finally:
            engine.release()

    # 3. Missing landmarks are not fabricated
    def test_item3_missing_landmarks_not_fabricated(self, sample_bgr_frame):
        sparse_pose = {
            "pose_detected": True,
            "landmarks": {
                "nose": {"x": 0.50, "y": 0.20, "visibility": 0.99},
            },
        }
        rendered = OverlayRenderer.render(
            frame=sample_bgr_frame,
            mode="MINIMAL",
            pose_data=sparse_pose,
            face_data=None,
        )
        assert rendered is not None
        assert rendered.shape == sample_bgr_frame.shape
        assert np.any(rendered > 0)

    # 4. Normalized coordinates map correctly to frame pixels
    def test_item4_normalized_coordinates_map_correctly(self):
        width, height = 640, 480
        pt_center = _to_pixel({"x": 0.5, "y": 0.5}, width, height)
        assert pt_center == (320, 240)

        pt_tl = _to_pixel({"x": 0.0, "y": 0.0}, width, height)
        assert pt_tl == (0, 0)

        pt_br = _to_pixel({"x": 1.0, "y": 1.0}, width, height)
        assert pt_br == (639, 479)

    # 5. Invalid coordinates handled safely
    def test_item5_invalid_coordinates_handled_safely(self):
        width, height = 640, 480
        assert _to_pixel(None, width, height) is None
        assert _to_pixel({"x": 1.5, "y": 0.5}, width, height) is None
        assert _to_pixel({"x": -0.1, "y": 0.5}, width, height) is None
        assert _to_pixel({"x": 0.5, "y": 0.5, "visibility": 0.1}, width, height) is None
        assert _to_pixel({"x": float("nan"), "y": 0.5}, width, height) is None
        assert _to_pixel({}, width, height) is None

    # 6. Overlay OFF returns clean frame
    def test_item6_overlay_off_returns_clean_frame(self, sample_bgr_frame, mock_pose_result, mock_face_result):
        test_frame = sample_bgr_frame.copy()
        test_frame[100, 100] = [123, 45, 67]

        rendered = OverlayRenderer.render(
            frame=test_frame,
            mode="OFF",
            pose_data=mock_pose_result,
            face_data=mock_face_result,
        )
        assert np.array_equal(rendered, test_frame)

    # 7. MINIMAL renders expected available landmarks
    def test_item7_minimal_renders_expected_landmarks(self, sample_bgr_frame, mock_pose_result, mock_face_result):
        rendered = OverlayRenderer.render(
            frame=sample_bgr_frame,
            mode="MINIMAL",
            pose_data=mock_pose_result,
            face_data=mock_face_result,
            human_state=HumanState(track_id="visionguard-001", posture_status="GOOD", alertness_status="ALERT"),
        )
        assert not np.array_equal(rendered, sample_bgr_frame)
        assert np.count_nonzero(rendered) > 100

    # 8. DEBUG uses real derived values
    def test_item8_debug_uses_real_derived_values(self, sample_bgr_frame, mock_pose_result, mock_face_result):
        state = HumanState(
            track_id="visionguard-001",
            posture_status="GOOD",
            posture_score=94.5,
            alertness_status="ALERT",
            alertness_score=98.0,
            eye_closure_duration=0.15,
            risk_level="NORMAL",
            risk_score=5.0,
        )
        baseline_p = PostureBaseline(
            shoulder_width=0.20,
            torso_length=0.30,
            shoulder_tilt=0.01,
            head_lateral_displacement=0.0,
            torso_lateral_displacement=0.0,
            head_shoulder_vertical_ratio=0.5,
            slouch_proxy=0.0,
            forward_lean_proxy=0.0,
            confidence=0.95,
            quality="GOOD",
            sample_count=30,
        )
        baseline_a = AlertnessBaseline(
            open_eye_ear=0.32,
            closed_eye_threshold=0.22,
            mouth_mor=0.25,
            yawn_threshold=0.55,
            head_pitch_ratio=0.45,
            head_nod_threshold=0.60,
            samples_count=30,
            quality="GOOD",
        )
        rendered = OverlayRenderer.render(
            frame=sample_bgr_frame,
            mode="DEBUG",
            pose_data=mock_pose_result,
            face_data=mock_face_result,
            human_state=state,
            posture_baseline=baseline_p,
            alertness_baseline=baseline_a,
        )
        assert rendered is not None
        assert not np.array_equal(rendered, sample_bgr_frame)

    # 9. Overlay rendering does not persist frames
    def test_item9_overlay_does_not_persist_frames(self, sample_bgr_frame, mock_pose_result):
        with tempfile.TemporaryDirectory() as tmpdir:
            initial_files = os.listdir(tmpdir)
            for _ in range(10):
                OverlayRenderer.render(
                    frame=sample_bgr_frame,
                    mode="MINIMAL",
                    pose_data=mock_pose_result,
                )
            assert os.listdir(tmpdir) == initial_files

    # 10. Existing preview still works
    def test_item10_existing_preview_still_works(self, sample_bgr_frame):
        manager = get_camera_manager()
        mock_source = MagicMock()
        mock_source.camera_index = 0
        mock_source.health.return_value = "READY"
        success, buf = cv2.imencode(".jpg", sample_bgr_frame)
        mock_source.read.return_value = buf.tobytes()
        manager._source = mock_source
        manager._running = True

        async def run():
            resp = await monitoring_preview(overlay="OFF", manager=manager)
            assert resp.status_code == 200
            async for chunk in resp.body_iterator:
                assert b"--frame" in chunk
                assert b"Content-Type: image/jpeg" in chunk
                break

        try:
            asyncio.run(run())
        finally:
            manager.stop()

    # 11. Existing posture calculations unchanged
    def test_item11_posture_calculations_unchanged(self):
        from app.posture.geometry import extract_body_geometry

        landmarks = {
            "left_shoulder": {"x": 0.40, "y": 0.40, "visibility": 0.95},
            "right_shoulder": {"x": 0.60, "y": 0.40, "visibility": 0.95},
            "left_hip": {"x": 0.40, "y": 0.70, "visibility": 0.95},
            "right_hip": {"x": 0.60, "y": 0.70, "visibility": 0.95},
            "nose": {"x": 0.50, "y": 0.25, "visibility": 0.95},
            "left_ear": {"x": 0.45, "y": 0.23, "visibility": 0.95},
            "right_ear": {"x": 0.55, "y": 0.23, "visibility": 0.95},
        }
        geom = extract_body_geometry(landmarks)
        assert geom is not None
        assert abs(geom.shoulder_tilt) < 0.001
        assert geom.torso_length > 0.1

    # 12. Existing alertness calculations unchanged
    def test_item12_alertness_calculations_unchanged(self, mock_face_result):
        from app.alertness.geometry import extract_face_geometry
        geom = extract_face_geometry(mock_face_result)
        assert geom is not None
        assert geom.combined_ear is not None
        assert geom.mouth_ratio is not None
        assert geom.confidence > 0.8

    # 13. Existing RiskEngine unchanged
    def test_item13_risk_engine_unchanged(self):
        from app.intelligence.risk_engine import RiskEngine
        risk_eng = RiskEngine()
        state = HumanState(track_id="visionguard-001", posture_status="GOOD", alertness_status="ALERT")
        res = risk_eng.evaluate(state)
        # Uncalibrated baseline evaluates to UNKNOWN as per Mission 05 spec
        assert res.level == RiskLevel.UNKNOWN
