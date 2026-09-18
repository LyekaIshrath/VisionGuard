import asyncio
from unittest.mock import patch, MagicMock
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.camera.manager import CameraManager, get_camera_manager
from app.camera.webcam_source import WebcamSource


class TestWebSocketDisconnectCleanup:
    """Regression tests for WebSocket disconnect handling."""

    def test_websocket_client_disconnect_clean_no_exception(self):
        """Verify normal client disconnect / refresh does not raise unhandled RuntimeError."""
        client = TestClient(app)
        with client.websocket_connect("/api/v1/monitoring/ws") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "status"
            # Reading second message (human_state)
            msg2 = ws.receive_json()
            assert msg2["type"] == "human_state"
            # Client closes abruptly (like browser page refresh/navigation)
            ws.close()

    def test_websocket_reconnect_cycle(self):
        """Verify client can connect, disconnect, and reconnect repeatedly."""
        client = TestClient(app)
        for _ in range(3):
            with client.websocket_connect("/api/v1/monitoring/ws") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "status"
                ws.close()


class TestTruthfulMonitoringAndCameraStates:
    """Regression tests for truthful monitoring states."""

    def test_camera_stopped_initial_state(self):
        """Verify stopped camera returns truthful STOPPED state."""
        manager = CameraManager(camera_index=99)
        status = manager.status()
        assert status["state"] == "STOPPED"
        assert status["camera"] == "NOT_CONFIGURED"
        assert status["frames_received"] == 0

    def test_camera_start_failure_truthful_state(self):
        """Verify when camera fails to open, CAMERA_ERROR is truthfully reported."""
        manager = CameraManager(camera_index=99)
        with patch.object(WebcamSource, "_open_capture", return_value=None):
            result = manager.start()
            assert result == "CAMERA_ERROR"
            status = manager.status()
            assert status["state"] == "CAMERA_ERROR"
            assert status["camera"] == "CAMERA_ERROR"

    def test_camera_opened_but_no_frames_reports_no_frames(self):
        """Verify when camera opens but frames stop, NO_FRAMES is truthfully reported."""
        source = WebcamSource(camera_index=0)
        source._running = True
        source._capture = MagicMock()
        source._capture.isOpened.return_value = True
        source._health_status = "NO_FRAMES"

        assert source.health() == "NO_FRAMES"

        manager = CameraManager(camera_index=0)
        manager._running = True
        manager._source = source

        status = manager.status()
        assert status["state"] == "NO_FRAMES"
        assert status["camera"] == "NO_FRAMES"

    def test_camera_ready_reports_running(self):
        """Verify when camera provides valid frames, RUNNING is truthfully reported."""
        source = WebcamSource(camera_index=0)
        source._running = True
        source._capture = MagicMock()
        source._capture.isOpened.return_value = True
        source._health_status = "READY"
        source._backend_used = "CAP_DSHOW"
        source._frames_received = 42

        manager = CameraManager(camera_index=0)
        manager._running = True
        manager._source = source

        status = manager.status()
        assert status["state"] == "RUNNING"
        assert status["camera"] == "READY"
        assert status["backend"] == "CAP_DSHOW"
        assert status["frames_received"] == 42


class TestLiveCameraPreview:
    """Regression tests for GET /api/v1/monitoring/preview endpoint."""

    def test_preview_stopped_returns_503(self):
        """Verify requesting preview when monitoring is stopped returns 503."""
        client = TestClient(app)
        manager = get_camera_manager()
        manager.stop()

        res = client.get("/api/v1/monitoring/preview")
        assert res.status_code == 503
        assert "not active" in res.json()["detail"].lower()

    def test_preview_running_yields_mjpeg_stream_without_second_videocapture(self):
        """Verify preview yields multipart/x-mixed-replace reusing WebcamSource without creating a 2nd capture."""
        from app.api.monitoring import monitoring_preview
        manager = get_camera_manager()

        mock_source = MagicMock()
        mock_source.camera_index = 0
        mock_source.health.return_value = "READY"
        fake_jpeg = b"\xff\xd8\xff\xe0fake_jpeg_data\xff\xd9"
        mock_source.read.return_value = fake_jpeg

        manager._source = mock_source
        manager._running = True

        async def check_stream():
            with patch("cv2.VideoCapture") as mock_vc:
                resp = await monitoring_preview(manager=manager)
                assert resp.status_code == 200
                assert "multipart/x-mixed-replace" in resp.media_type
                assert resp.headers["Cache-Control"] == "no-cache, no-store, must-revalidate"

                async for chunk in resp.body_iterator:
                    assert b"--frame" in chunk
                    assert b"Content-Type: image/jpeg" in chunk
                    assert fake_jpeg in chunk
                    break

                mock_vc.assert_not_called()

        asyncio.run(check_stream())
        manager.stop()
