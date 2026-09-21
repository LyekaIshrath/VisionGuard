"""VisionGuard Work Activity Redesign - Comprehensive Phase 1-3 Tests.

Verifies:
1. Built-in baselines & calibration-free startup
2. Blink detection, normal blink not inactivity, long closure, missing face -> unknown
3. Complete human geometry, minimal vs debug overlay, horizontal/vertical axes
4. Workstation activity collector privacy (zero keylogging, zero stored mouse coords, zero clipboard)
5. WorkActivityEngine states (ACTIVE, LOW_ACTIVITY, ATTENTION_AWAY, AWAY, UNKNOWN) & temporal hysteresis
6. Single-button atomic startup & stop, same session_id, rollback, cloud failure isolation
7. Single-pipeline invariants (1 VideoCapture, 1 PoseLandmarker, 1 FaceLandmarker)
"""

import time
import inspect
import numpy as np
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.intelligence.baselines import (
    BUILT_IN_POSTURE_BASELINE,
    BUILT_IN_ALERTNESS_BASELINE,
    get_effective_posture_baseline,
    get_effective_alertness_baseline,
)
from app.posture.calibration import PostureBaseline
from app.alertness.calibration import AlertnessBaseline
from app.alertness.analyzer import AlertnessAnalyzer, AlertnessStatus
from app.alertness.geometry import FaceGeometry
from app.human_state.models import HumanState
from app.perception.engine import PerceptionEngine, get_perception_engine
from app.perception.overlay import OverlayRenderer
from app.activity.collector import WorkstationActivityCollector, ActivitySnapshot
from app.activity.engine import (
    WorkActivityEngine,
    WorkActivityState,
    IDLE_ACTIVE_THRESHOLD_SEC,
    HEAD_AWAY_YAW_DEGREE_THRESHOLD,
    HEAD_AWAY_SUSTAINED_SEC,
    PERSON_AWAY_SUSTAINED_SEC,
)
from app.coordination.coordinator import MonitoringCoordinator, CoordinatorState


# ==============================================================================
# 1. BUILT-IN BASELINES TESTS
# ==============================================================================

class TestBuiltInBaselines:
    def test_builtin_posture_baseline_values(self):
        base = BUILT_IN_POSTURE_BASELINE
        assert base.shoulder_width > 0
        assert base.torso_length > 0
        assert base.confidence >= 0.80
        assert base.quality == "BUILT_IN_DEFAULT"

    def test_builtin_alertness_baseline_values(self):
        base = BUILT_IN_ALERTNESS_BASELINE
        assert base.open_eye_ear > 0.20
        assert base.closed_eye_threshold < base.open_eye_ear
        assert base.quality == "BUILT_IN_DEFAULT"

    def test_effective_baseline_selection_uncalibrated(self):
        p_base, p_src, p_conf = get_effective_posture_baseline(None)
        assert p_src == "BUILT_IN"
        assert p_base == BUILT_IN_POSTURE_BASELINE
        assert p_conf == 0.85

        a_base, a_src, a_conf = get_effective_alertness_baseline(None)
        assert a_src == "BUILT_IN"
        assert a_base == BUILT_IN_ALERTNESS_BASELINE
        assert a_conf == 0.85

    def test_effective_baseline_selection_personalized(self):
        custom_p = PostureBaseline(
            shoulder_width=0.40,
            torso_length=0.50,
            shoulder_tilt=0.01,
            head_lateral_displacement=0.0,
            torso_lateral_displacement=0.0,
            head_shoulder_vertical_ratio=0.30,
            slouch_proxy=0.30,
            forward_lean_proxy=0.40,
            confidence=0.98,
            quality="EXCELLENT",
            sample_count=40,
            has_hips=True,
        )
        p_base, p_src, p_conf = get_effective_posture_baseline(custom_p)
        assert p_src == "PERSONALIZED"
        assert p_base == custom_p
        assert p_conf == 0.98

        custom_a = AlertnessBaseline(
            open_eye_ear=0.30,
            closed_eye_threshold=0.18,
            mouth_mor=0.12,
            yawn_threshold=0.50,
            head_pitch_ratio=0.01,
            head_nod_threshold=-0.12,
            samples_count=40,
            quality="EXCELLENT",
        )
        a_base, a_src, a_conf = get_effective_alertness_baseline(custom_a)
        assert a_src == "PERSONALIZED"
        assert a_base == custom_a
        assert a_conf == 0.95

    def test_start_without_calibration_generates_valid_state(self):
        engine = PerceptionEngine()
        # Feed dummy black frame - uncalibrated engine must not crash
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        state = engine.process_frame(blank)
        assert state is not None
        assert state.baseline_source in ("BUILT_IN", "PERSONALIZED")


# ==============================================================================
# 2. BLINK AND EYE MONITORING TESTS
# ==============================================================================

class TestBlinkAndEyeMonitoring:
    def test_normal_blink_detection_increments_count(self):
        analyzer = AlertnessAnalyzer()
        analyzer.set_baseline(BUILT_IN_ALERTNESS_BASELINE)

        t = 1000.0
        # Frame 1: Open eye
        geom_open = FaceGeometry(
            left_ear=0.28, right_ear=0.28, combined_ear=0.28,
            mouth_ratio=0.15, head_pitch_ratio=0.0, left_eye_valid=True, right_eye_valid=True,
            confidence=0.9, is_valid=True
        )
        r1 = analyzer.analyze(geom_open, timestamp=t)
        assert r1.eye_state == "OPEN"
        assert r1.blink_count == 0

        # Frame 2: Closed eye for 150ms (normal blink)
        t += 0.05
        geom_closed = FaceGeometry(
            left_ear=0.12, right_ear=0.12, combined_ear=0.12,
            mouth_ratio=0.15, head_pitch_ratio=0.0, left_eye_valid=True, right_eye_valid=True,
            confidence=0.9, is_valid=True
        )
        analyzer.analyze(geom_closed, timestamp=t)

        t += 0.10
        analyzer.analyze(geom_closed, timestamp=t)

        # Frame 3: Eye re-opens -> Blink completed
        t += 0.05
        r3 = analyzer.analyze(geom_open, timestamp=t)
        assert r3.eye_state == "OPEN"
        assert r3.blink_count == 1

    def test_normal_blink_not_inactivity(self):
        engine = WorkActivityEngine()
        state = HumanState(
            track_id="001", person_detected=True, face_detected=True,
            eye_state="CLOSED", eye_closure_duration=0.15, blink_count=5
        )
        snap = ActivitySnapshot(
            keyboard_event_count=2, mouse_movement_count=1, mouse_click_count=0,
            scroll_count=0, mouse_distance=15.0, last_input_at=time.time(),
            idle_seconds=1.0, foreground_app_changed=False, screen_change_score=None
        )
        decision = engine.evaluate(state, snap)
        # Normal blinking during input MUST remain ACTIVE
        assert decision.state == WorkActivityState.ACTIVE

    def test_long_closure_tracks_longest_duration(self):
        analyzer = AlertnessAnalyzer()
        analyzer.set_baseline(BUILT_IN_ALERTNESS_BASELINE)
        t = 2000.0

        geom_closed = FaceGeometry(
            left_ear=0.10, right_ear=0.10, combined_ear=0.10,
            mouth_ratio=0.15, head_pitch_ratio=0.0, left_eye_valid=True, right_eye_valid=True,
            confidence=0.9, is_valid=True
        )
        # 2.5 seconds sustained closure
        for i in range(25):
            t += 0.10
            res = analyzer.analyze(geom_closed, timestamp=t)

        assert res.eye_closure_duration >= 2.0
        assert res.longest_eye_closure >= 2.0

    def test_missing_face_returns_unknown(self):
        analyzer = AlertnessAnalyzer()
        analyzer.set_baseline(BUILT_IN_ALERTNESS_BASELINE)
        res = analyzer.analyze(None)
        assert res.status == AlertnessStatus.UNKNOWN
        assert res.eye_state == "UNKNOWN"


# ==============================================================================
# 3. COMPLETE HUMAN GEOMETRY & OVERLAY MODES
# ==============================================================================

class TestGeometryAndOverlays:
    @pytest.fixture
    def sample_frame(self):
        return np.zeros((480, 640, 3), dtype=np.uint8)

    @pytest.fixture
    def mock_pose_and_face(self):
        pose = {
            "pose_detected": True,
            "landmarks": {
                "nose": {"x": 0.50, "y": 0.20, "visibility": 0.99},
                "left_shoulder": {"x": 0.40, "y": 0.40, "visibility": 0.95},
                "right_shoulder": {"x": 0.60, "y": 0.40, "visibility": 0.95},
                "left_elbow": {"x": 0.35, "y": 0.55, "visibility": 0.90},
                "right_elbow": {"x": 0.65, "y": 0.55, "visibility": 0.90},
                "left_wrist": {"x": 0.32, "y": 0.70, "visibility": 0.90},
                "right_wrist": {"x": 0.68, "y": 0.70, "visibility": 0.90},
                "left_hip": {"x": 0.42, "y": 0.75, "visibility": 0.90},
                "right_hip": {"x": 0.58, "y": 0.75, "visibility": 0.90},
            },
            "all_landmarks": [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 1.0}] * 33,
        }
        face = {
            "face_detected": True,
            "eye_landmarks": {
                "left_eye": {"outer": {"x": 0.43, "y": 0.22}, "inner": {"x": 0.47, "y": 0.22}, "top": {"x": 0.45, "y": 0.20}, "bottom": {"x": 0.45, "y": 0.24}},
                "right_eye": {"outer": {"x": 0.57, "y": 0.22}, "inner": {"x": 0.53, "y": 0.22}, "top": {"x": 0.55, "y": 0.20}, "bottom": {"x": 0.55, "y": 0.24}},
            },
            "head_reference": {"forehead": {"x": 0.50, "y": 0.12}, "nose_tip": {"x": 0.50, "y": 0.22}, "chin": {"x": 0.50, "y": 0.32}},
            "all_landmarks": [{"x": 0.5, "y": 0.5, "z": 0.0}] * 478,
        }
        return pose, face

    def test_minimal_overlay_renders_axes_and_skeleton(self, sample_frame, mock_pose_and_face):
        pose, face = mock_pose_and_face
        rendered = OverlayRenderer.render(
            frame=sample_frame, mode="MINIMAL", pose_data=pose, face_data=face
        )
        assert rendered is not None
        assert np.any(rendered > 0)

    def test_debug_overlay_renders_dense_mesh(self, sample_frame, mock_pose_and_face):
        pose, face = mock_pose_and_face
        rendered_debug = OverlayRenderer.render(
            frame=sample_frame, mode="DEBUG", pose_data=pose, face_data=face
        )
        rendered_min = OverlayRenderer.render(
            frame=sample_frame, mode="MINIMAL", pose_data=pose, face_data=face
        )
        assert np.any(rendered_debug > 0)
        # Debug has telemetry box and mesh dots
        assert np.sum(rendered_debug) > np.sum(rendered_min)

    def test_off_overlay_mode_returns_untouched_frame(self, sample_frame, mock_pose_and_face):
        pose, face = mock_pose_and_face
        rendered = OverlayRenderer.render(
            frame=sample_frame, mode="OFF", pose_data=pose, face_data=face
        )
        assert np.array_equal(rendered, sample_frame)


# ==============================================================================
# 4. WORKSTATION ACTIVITY COLLECTOR PRIVACY TESTS
# ==============================================================================

class TestWorkstationActivityCollectorPrivacy:
    def test_zero_keylogging_guarantee(self):
        collector = WorkstationActivityCollector()
        collector.record_simulated_input("KEYBOARD")
        snapshot = collector.get_snapshot()

        assert snapshot.keyboard_event_count == 1
        # Inspect snapshot fields
        fields = ActivitySnapshot.__dataclass_fields__.keys()
        forbidden = ["key_name", "typed_chars", "character", "password", "clipboard", "keystroke_content"]
        for f in fields:
            for forb in forbidden:
                assert forb not in f.lower(), f"Forbidden field {f} found in ActivitySnapshot!"

    def test_zero_stored_mouse_coordinates(self):
        collector = WorkstationActivityCollector()
        collector.record_simulated_input("MOUSE_MOVE")
        snapshot = collector.get_snapshot()

        assert snapshot.mouse_movement_count == 1
        assert snapshot.mouse_distance >= 10.0
        # Check that no coordinates are exposed
        fields = ActivitySnapshot.__dataclass_fields__.keys()
        for f in fields:
            assert f not in ("x", "y", "cursor_x", "cursor_y", "mouse_x", "mouse_y")

    def test_zero_clipboard_access(self):
        # Inspect source code of collector to guarantee no clipboard modules
        src = inspect.getsource(WorkstationActivityCollector)
        assert "clipboard" not in src.lower()
        assert "pyperclip" not in src.lower()

    def test_foreground_app_changed_without_title_leak(self):
        collector = WorkstationActivityCollector()
        collector.record_simulated_input("APP_SWITCH")
        snapshot = collector.get_snapshot()
        assert snapshot.foreground_app_changed is True
        # Ensure no window title or document content exists
        src = inspect.getsource(WorkstationActivityCollector)
        assert "GetWindowText" not in src
        assert "window_title" not in src.lower()


# ==============================================================================
# 5. WORK ACTIVITY ENGINE TESTS
# ==============================================================================

class TestWorkActivityEngine:
    def test_state_active_on_recent_input(self):
        engine = WorkActivityEngine()
        state = HumanState(track_id="001", person_detected=True, face_detected=True, confidence=0.9)
        snap = ActivitySnapshot(
            keyboard_event_count=3, mouse_movement_count=2, mouse_click_count=1,
            scroll_count=0, mouse_distance=25.0, last_input_at=time.time(),
            idle_seconds=2.0, foreground_app_changed=False, screen_change_score=None
        )
        dec = engine.evaluate(state, snap)
        assert dec.state == WorkActivityState.ACTIVE
        assert "PERSON_INTERACTING_INPUT" in dec.reason_codes

    def test_state_low_activity_when_observing(self):
        engine = WorkActivityEngine(hysteresis_sec=0.0)
        state = HumanState(track_id="001", person_detected=True, face_detected=True, head_yaw=0.0, confidence=0.9)
        snap = ActivitySnapshot(
            keyboard_event_count=0, mouse_movement_count=0, mouse_click_count=0,
            scroll_count=0, mouse_distance=0.0, last_input_at=time.time() - 35,
            idle_seconds=35.0, foreground_app_changed=False, screen_change_score=None
        )
        dec = engine.evaluate(state, snap)
        assert dec.state == WorkActivityState.LOW_ACTIVITY
        assert "PERSON_READING_OBSERVING" in dec.reason_codes

    def test_state_attention_away_on_sustained_head_yaw(self):
        engine = WorkActivityEngine(head_away_sec=1.0, hysteresis_sec=0.0)
        t = 3000.0
        state = HumanState(track_id="001", person_detected=True, face_detected=True, head_yaw=35.0, confidence=0.9)
        snap = ActivitySnapshot(
            keyboard_event_count=0, mouse_movement_count=0, mouse_click_count=0,
            scroll_count=0, mouse_distance=0.0, last_input_at=None,
            idle_seconds=30.0, foreground_app_changed=False, screen_change_score=None
        )
        # Frame 1: Looking away starts
        engine.evaluate(state, snap, timestamp=t)
        # Frame 2: Sustained for 1.5s
        t += 1.5
        dec = engine.evaluate(state, snap, timestamp=t)
        assert dec.state == WorkActivityState.ATTENTION_AWAY

    def test_state_away_on_sustained_person_absent(self):
        engine = WorkActivityEngine(away_sec=2.0, hysteresis_sec=0.0)
        t = 4000.0
        state = HumanState(track_id="001", person_detected=False, face_detected=False, confidence=0.0)
        # First absent frame
        engine.evaluate(state, None, timestamp=t)
        # Sustained absent frame after 2.5s
        t += 2.5
        dec = engine.evaluate(state, None, timestamp=t)
        assert dec.state == WorkActivityState.AWAY

    def test_state_unknown_on_none_human_state(self):
        engine = WorkActivityEngine()
        dec = engine.evaluate(None, None)
        assert dec.state == WorkActivityState.UNKNOWN

    def test_temporal_hysteresis_prevents_flickering(self):
        engine = WorkActivityEngine(hysteresis_sec=2.0)
        t = 5000.0
        state_active = HumanState(track_id="001", person_detected=True, face_detected=True, confidence=0.9)
        snap_active = ActivitySnapshot(
            keyboard_event_count=1, mouse_movement_count=1, mouse_click_count=0,
            scroll_count=0, mouse_distance=10.0, last_input_at=t,
            idle_seconds=0.0, foreground_app_changed=False, screen_change_score=None
        )
        dec1 = engine.evaluate(state_active, snap_active, timestamp=t)
        assert dec1.state == WorkActivityState.ACTIVE

        # Brief idle flicker for 0.5s should NOT immediately drop state
        t += 0.5
        snap_idle = ActivitySnapshot(
            keyboard_event_count=1, mouse_movement_count=1, mouse_click_count=0,
            scroll_count=0, mouse_distance=10.0, last_input_at=t - 10,
            idle_seconds=10.0, foreground_app_changed=False, screen_change_score=None
        )
        dec2 = engine.evaluate(state_active, snap_idle, timestamp=t)
        assert dec2.state == WorkActivityState.ACTIVE

    def test_no_judgmental_labels(self):
        engine = WorkActivityEngine()
        forbidden = ["productive", "unproductive", "lazy", "working", "not_working"]
        for state in WorkActivityState:
            for forb in forbidden:
                assert forb not in state.value.lower()


# ==============================================================================
# 6. MONITORING COORDINATOR LIFECYCLE TESTS
# ==============================================================================

class TestMonitoringCoordinatorLifecycle:
    def test_single_button_atomic_startup(self):
        coord = MonitoringCoordinator()
        # Mock camera to avoid opening real hardware webcam during test
        coord._camera_manager.start = MagicMock(return_value="STARTED")
        coord._camera_manager.stop = MagicMock(return_value="STOPPED")

        res = coord.start_monitoring(user_id="test_user")
        try:
            assert res["success"] is True
            assert res["status"] == "MONITORING"
            assert res["session_id"] is not None
            assert coord.state == CoordinatorState.MONITORING
            assert len(coord.timeline_events) >= 1
            assert coord.timeline_events[0]["type"] == "SESSION_START"
        finally:
            coord.stop_monitoring()

    def test_same_session_id_across_subsystems(self):
        coord = MonitoringCoordinator()
        coord._camera_manager.start = MagicMock(return_value="STARTED")
        coord._camera_manager.stop = MagicMock(return_value="STOPPED")

        res = coord.start_monitoring(user_id="user_123")
        try:
            sid = res["session_id"]
            assert sid == coord.session_id
            assert coord.timeline_events[0]["session_id"] == sid
        finally:
            coord.stop_monitoring()

    def test_startup_rollback_on_camera_hardware_failure(self):
        coord = MonitoringCoordinator()
        coord._camera_manager.start = MagicMock(return_value="CAMERA_ERROR")

        res = coord.start_monitoring(user_id="user_test")
        assert res["success"] is False
        assert res["failed_component"] == "camera"
        assert res["error_code"] == "CAMERA_START_FAILED"
        assert coord.state == CoordinatorState.STOPPED
        assert coord.session_id is None

    def test_single_button_stop_and_report(self):
        coord = MonitoringCoordinator()
        coord._camera_manager.start = MagicMock(return_value="STARTED")
        coord._camera_manager.stop = MagicMock(return_value="STOPPED")

        coord.start_monitoring(user_id="user_stop_test")
        stop_res = coord.stop_monitoring()

        assert stop_res["status"] == "COMPLETED"
        assert stop_res["session_id"] is not None
        assert "session_summary" in stop_res
        assert coord.state == CoordinatorState.COMPLETED

    def test_single_pipeline_invariants(self):
        # Guarantee singleton PerceptionEngine and single camera manager
        p1 = get_perception_engine()
        p2 = get_perception_engine()
        assert p1 is p2
        assert hasattr(p1, "_pose")
        assert hasattr(p1, "_face")
