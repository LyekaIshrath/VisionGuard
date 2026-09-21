from __future__ import annotations

import time
import numpy as np
import pytest

from app.human_state.models import HumanState
from app.activity.collector import WorkstationActivityCollector, ActivitySnapshot
from app.activity.engine import WorkActivityEngine, WorkActivityState, WorkActivityConfig
from app.perception.overlay import OverlayRenderer


class TestPhaseBWorkSignalsAndPrivacy:
    """Verifies Phase B: Work Observation Engine, Screen Activity, and Privacy Guarantees."""

    def test_engaged_requires_recent_input(self):
        """ENGAGED requires person present AND genuine workstation input."""
        engine = WorkActivityEngine(hysteresis_sec=0.0)
        state = HumanState(track_id="001", person_detected=True, face_detected=True, head_yaw=0.0, confidence=0.9)
        now = time.time()

        # Case 1: Input within 15s -> ENGAGED
        snap_with_input = ActivitySnapshot(
            keyboard_event_count=5, mouse_movement_count=10, mouse_click_count=2,
            scroll_count=1, mouse_distance=50.0, last_input_at=now,
            idle_seconds=2.0, foreground_app_changed=False, screen_change_score=5.0,
            screen_activity_level="LOW_CHANGE", last_screen_change_at=now,
        )
        dec = engine.evaluate(state, snap_with_input, now=now)
        assert dec.state == WorkActivityState.ENGAGED

        # Case 2: Idle 40s with screen CHANGING -> Must NOT be ENGAGED (Screen changes alone do NOT trigger ENGAGED)
        snap_screen_only = ActivitySnapshot(
            keyboard_event_count=0, mouse_movement_count=0, mouse_click_count=0,
            scroll_count=0, mouse_distance=0.0, last_input_at=now - 40,
            idle_seconds=40.0, foreground_app_changed=False, screen_change_score=25.0,
            screen_activity_level="CHANGING", last_screen_change_at=now,
        )
        dec2 = engine.evaluate(state, snap_screen_only, now=now)
        assert dec2.state == WorkActivityState.OBSERVING
        assert dec2.state != WorkActivityState.ENGAGED

    def test_blinking_never_triggers_engaged(self):
        """Blinking alone must NEVER independently cause ENGAGED."""
        engine = WorkActivityEngine(hysteresis_sec=0.0)
        # Person present, idle 35s, high blink count
        state = HumanState(
            track_id="001", person_detected=True, face_detected=True, head_yaw=0.0,
            confidence=0.9, blink_count=45, eye_state="OPEN"
        )
        now = time.time()
        snap = ActivitySnapshot(
            keyboard_event_count=0, mouse_movement_count=0, mouse_click_count=0,
            scroll_count=0, mouse_distance=0.0, last_input_at=now - 35,
            idle_seconds=35.0, foreground_app_changed=False, screen_change_score=0.0,
            screen_activity_level="STATIC", last_screen_change_at=None,
        )
        dec = engine.evaluate(state, snap, now=now)
        assert dec.state == WorkActivityState.OBSERVING
        assert dec.state != WorkActivityState.ENGAGED

    def test_screen_privacy_zero_storage(self):
        """Screen collector strictly exposes only derived scores and levels; zero image storage."""
        collector = WorkstationActivityCollector()
        collector.record_simulated_screen_change("CHANGING", score=18.5)
        snap = collector.get_snapshot()

        assert snap.screen_activity_level == "CHANGING"
        assert snap.screen_change_score == 18.5
        assert snap.last_screen_change_at is not None

        # Verify no screenshot/image attributes exist in snapshot
        assert not hasattr(snap, "screenshot")
        assert not hasattr(snap, "image")
        assert not hasattr(snap, "raw_pixels")

    def test_clean_human_geometry_rendering(self):
        """Verify minimal overlay renders clean reference axes without crashing or fabricating points."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        pose_data = {
            "pose_detected": True,
            "landmarks": {
                "nose": {"x": 0.5, "y": 0.3, "visibility": 0.95},
                "left_shoulder": {"x": 0.4, "y": 0.5, "visibility": 0.9},
                "right_shoulder": {"x": 0.6, "y": 0.5, "visibility": 0.9},
                "left_elbow": {"x": 0.35, "y": 0.65, "visibility": 0.85},
                "right_elbow": {"x": 0.65, "y": 0.65, "visibility": 0.85},
                "left_wrist": {"x": 0.3, "y": 0.75, "visibility": 0.8},
                "right_wrist": {"x": 0.7, "y": 0.75, "visibility": 0.8},
            }
        }
        face_data = {
            "face_detected": True,
            "eye_landmarks": {
                "left_eye": {"outer": {"x": 0.45, "y": 0.28}, "inner": {"x": 0.48, "y": 0.28}},
                "right_eye": {"outer": {"x": 0.55, "y": 0.28}, "inner": {"x": 0.52, "y": 0.28}},
            }
        }

        rendered = OverlayRenderer.render(frame, mode="MINIMAL", pose_data=pose_data, face_data=face_data)
        assert rendered is not None
        assert rendered.shape == (480, 640, 3)
        assert np.any(rendered > 0)  # Geometry drawn
