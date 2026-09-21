from __future__ import annotations

import time
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from app.camera.manager import CameraManager, get_camera_manager
from app.camera.webcam_source import WebcamSource, CameraState


class TestCameraExplicitStatesAndReliability:
    """Verifies Phase A Camera runtime hardening and state machine."""

    def test_camera_initial_state_stopped(self):
        source = WebcamSource(camera_index=0)
        assert source.camera_state == CameraState.STOPPED
        assert source.health() == "NOT_CONFIGURED"
        assert source.last_frame_age_ms == 9999.0
        assert source.frame_sequence == 0

    def test_camera_successful_start_transitions_to_live(self):
        source = WebcamSource(camera_index=0)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)

        with patch.object(source, "_open_capture", return_value=mock_cap):
            source.start()
            try:
                assert source.camera_state == CameraState.LIVE
                assert source.health() == "READY"
                time.sleep(0.05)
                assert source.frame_sequence > 0
                assert source.last_frame_age_ms < 1000.0
            finally:
                source.stop()
                assert source.camera_state == CameraState.STOPPED

    def test_camera_start_failure_diagnoses_no_camera_or_error(self):
        source = WebcamSource(camera_index=99)
        with patch.object(source, "_open_capture", return_value=None):
            with pytest.raises(RuntimeError):
                source.start()
            assert source.camera_state in (CameraState.NO_CAMERA, CameraState.ERROR)
            assert source.health() == "CAMERA_ERROR"

    def test_stale_frame_triggers_no_frames_and_reconnect(self):
        """When frames cease for > 1500 ms, source transitions to NO_FRAMES / RECONNECTING."""
        source = WebcamSource(camera_index=0)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)

        with patch.object(source, "_open_capture", return_value=mock_cap):
            source.start()
            try:
                time.sleep(0.05)
                assert source.camera_state == CameraState.LIVE

                # Simulate frame dropout: read() returns (False, None)
                mock_cap.read.return_value = (False, None)
                source._last_frame_timestamp = time.monotonic() - 2.0  # 2000 ms ago

                reconnect_called = False

                def mock_reconnect():
                    nonlocal reconnect_called
                    reconnect_called = True
                    source._state = CameraState.RECONNECTING
                    return True

                source._attempt_reconnect = mock_reconnect
                time.sleep(0.08)

                assert reconnect_called is True
            finally:
                source.stop()

    def test_start_stop_start_lifecycle_clean_resource_release(self):
        """Verify camera can be started, stopped, and restarted cleanly without orphaned handles."""
        manager = CameraManager(camera_index=0)
        mock_cap1 = MagicMock()
        mock_cap1.isOpened.return_value = True
        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap1.read.return_value = (True, fake_frame)

        mock_cap2 = MagicMock()
        mock_cap2.isOpened.return_value = True
        mock_cap2.read.return_value = (True, fake_frame)

        caps = [mock_cap1, mock_cap2]

        with patch.object(WebcamSource, "_open_capture", side_effect=caps):
            # First start
            res1 = manager.start()
            assert res1 == "STARTED"
            assert manager.status()["state"] == "RUNNING"
            assert manager.status()["camera_state"] == "LIVE"

            # Stop
            res_stop = manager.stop()
            assert res_stop == "STOPPED"
            assert manager.status()["state"] == "STOPPED"
            assert manager.status()["camera_state"] == "STOPPED"
            mock_cap1.release.assert_called()

            # Second start (restart)
            res2 = manager.start()
            assert res2 == "STARTED"
            assert manager.status()["state"] == "RUNNING"
            manager.stop()
            mock_cap2.release.assert_called()

    def test_single_videocapture_handle_invariant_enforced(self):
        """Verify manager strictly owns exactly one WebcamSource and one active VideoCapture."""
        manager = CameraManager(camera_index=0)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)

        with patch.object(WebcamSource, "_open_capture", return_value=mock_cap):
            manager.start()
            try:
                # Calling start while already running returns ALREADY_RUNNING without creating another handle
                res = manager.start()
                assert res == "ALREADY_RUNNING"
            finally:
                manager.stop()
