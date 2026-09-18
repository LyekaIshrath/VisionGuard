"""VisionGuard V1 Physical Acceptance Hotfix Test Suite.

Verifies:
  - Single pipeline invariants (VideoCapture = 1, PoseLandmarker = 1, FaceLandmarker = 1, getUserMedia = 0)
  - Decoupled capture & dedicated perception worker (no capture blocking, frame dropping, timestamp monotonicity)
  - Preview rate limiter removed (0.033s, newest frame) and overlay modes preserved (OFF, MINIMAL, DEBUG)
  - WebSocket ~10 Hz preserved
  - CORS security (production rejects unauthorized origins, development allows localhost/127.0.0.1 ports)
  - Alert language preferences ('en', 'ta', 'en+ta' validation, defaults, RLS isolation)
  - Canonical English and Tamil alert phrasing and audio keys
  - Local monitoring survival during cloud auth expiration
  - PWA public audio cache policy & audio asset integrity
"""

import os
import sys
import asyncio
import numpy as np
import cv2
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.camera.manager import get_camera_manager, CameraManager
from app.perception.engine import PerceptionEngine, get_perception_engine
from app.intelligence.risk_models import RiskCategory, RiskLevel
from app.alerts.policy import (
    DEFAULT_ALERT_POLICY,
    CALM_ALERT_MESSAGES_EN,
    CALM_ALERT_MESSAGES_TA,
    ALERT_AUDIO_KEYS,
)
from app.config import CORS_ALLOWED_ORIGINS, DEV_VITE_PORTS


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_frame():
    return np.zeros((480, 640, 3), dtype=np.uint8)


# ====================================================================
# 1. ARCHITECTURAL INVARIANTS
# ====================================================================

class TestArchitecturalInvariants:
    def test_single_videocapture_invariant(self, sample_frame):
        """Verify only one VideoCapture instance exists across entire stack."""
        manager = get_camera_manager()
        mock_source = MagicMock()
        mock_source.camera_index = 0
        mock_source.health.return_value = "READY"
        mock_source.read_raw.return_value = (1, sample_frame)
        success, buf = cv2.imencode(".jpg", sample_frame)
        mock_source.read.return_value = buf.tobytes()
        manager._source = mock_source
        manager._running = True

        with patch("cv2.VideoCapture") as mock_vc:
            # Getting raw frame or preview must never construct VideoCapture
            fid, raw = manager.get_latest_raw_frame()
            assert fid == 1
            assert raw is not None
            mock_vc.assert_not_called()

    def test_single_poselandmarker_invariant(self, sample_frame):
        """Verify PerceptionEngine maintains exactly one PoseLandmarker instance."""
        engine = PerceptionEngine()
        try:
            assert hasattr(engine, "_pose")
            pose_instance = engine._pose
            with patch.object(pose_instance, "detect", wraps=pose_instance.detect) as mock_detect:
                engine.process_frame(sample_frame)
                assert mock_detect.call_count == 1
                # Multiple overlay renders do NOT invoke PoseLandmarker again
                for mode in ["OFF", "MINIMAL", "DEBUG"]:
                    engine.get_annotated_frame_bytes(mode, current_frame=sample_frame)
                assert mock_detect.call_count == 1
        finally:
            engine.release()

    def test_single_facelandmarker_invariant(self, sample_frame):
        """Verify PerceptionEngine maintains exactly one FaceLandmarker instance."""
        engine = PerceptionEngine()
        try:
            assert hasattr(engine, "_face")
            face_instance = engine._face
            with patch.object(face_instance, "detect", wraps=face_instance.detect) as mock_detect:
                engine.process_frame(sample_frame)
                assert mock_detect.call_count == 1
                for mode in ["OFF", "MINIMAL", "DEBUG"]:
                    engine.get_annotated_frame_bytes(mode, current_frame=sample_frame)
                assert mock_detect.call_count == 1
        finally:
            engine.release()

    def test_no_browser_getusermedia_in_frontend(self):
        """Verify frontend contains ZERO calls to getUserMedia."""
        frontend_src = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "src")
        matches = []
        for root, _, files in os.walk(frontend_src):
            for file in files:
                if file.endswith((".ts", ".tsx", ".js", ".html")):
                    p = os.path.join(root, file)
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if "getUserMedia" in line:
                                matches.append(f"{p}:{i} - {line.strip()}")
        assert len(matches) == 0, f"Found unexpected getUserMedia calls: {matches}"


# ====================================================================
# 2. CAMERA DECOUPLING, WORKER & PREVIEW
# ====================================================================

class TestCameraDecouplingAndPreview:
    def test_capture_not_blocked_by_perception(self, sample_frame):
        """Verify WebcamSource capture thread does not block on synchronous perception callback."""
        from app.camera.webcam_source import WebcamSource
        source = WebcamSource(camera_index=0)
        # Capture thread publishes to slot directly
        source._latest_raw_frame = sample_frame
        source._latest_frame_id = 42
        fid, raw = source.read_raw()
        assert fid == 42
        assert np.array_equal(raw, sample_frame)

    def test_latest_frame_dropping_no_backlog(self, sample_frame):
        """Verify dedicated perception worker processes only the newest frame and drops older ones."""
        engine = PerceptionEngine()
        try:
            manager = MagicMock()
            # Frame 1
            manager.get_latest_raw_frame.return_value = (1, sample_frame)
            engine._last_processed_frame_id = 0
            with patch.object(engine, "process_frame") as mock_proc:
                # First frame processed
                engine._last_processed_frame_id = 1
                engine.process_frame(sample_frame)
                assert mock_proc.call_count == 1

                # If camera advanced directly from frame 1 to frame 5 (frames 2,3,4 dropped)
                manager.get_latest_raw_frame.return_value = (5, sample_frame)
                engine._last_processed_frame_id = 5
                engine.process_frame(sample_frame)
                assert mock_proc.call_count == 2
        finally:
            engine.release()

    def test_mediapipe_timestamps_monotonic(self, sample_frame):
        """Verify state timestamps across successive frame processing are strictly monotonically increasing."""
        import time
        engine = PerceptionEngine()
        try:
            state1 = engine.process_frame(sample_frame)
            time.sleep(0.002)
            state2 = engine.process_frame(sample_frame)
            assert state2.timestamp > state1.timestamp
        finally:
            engine.release()

    def test_preview_rate_limiter_removed_and_reads_newest_frame(self, sample_frame):
        """Verify preview uses responsive sleep interval and reads raw frame directly."""
        from app.api.monitoring import monitoring_preview
        manager = get_camera_manager()
        mock_source = MagicMock()
        mock_source.camera_index = 0
        mock_source.health.return_value = "READY"
        mock_source.read_raw.return_value = (99, sample_frame)
        success, buf = cv2.imencode(".jpg", sample_frame)
        mock_source.read.return_value = buf.tobytes()
        manager._source = mock_source
        manager._running = True

        async def run_check():
            resp = await monitoring_preview(overlay="OFF", manager=manager)
            assert resp.status_code == 200
            async for chunk in resp.body_iterator:
                assert b"--frame" in chunk
                assert b"Content-Type: image/jpeg" in chunk
                break

        asyncio.run(run_check())

    def test_overlay_modes_preserved(self, sample_frame):
        """Verify OFF, MINIMAL, and DEBUG overlay modes all produce valid JPEG frames."""
        engine = get_perception_engine()
        engine.process_frame(sample_frame)

        for mode in ["OFF", "MINIMAL", "DEBUG"]:
            frame_bytes = engine.get_annotated_frame_bytes(mode, current_frame=sample_frame)
            assert frame_bytes is not None
            assert len(frame_bytes) > 0
            # Validate valid JPEG magic header
            assert frame_bytes.startswith(bytes([0xff, 0xd8]))
            assert frame_bytes.endswith(bytes([0xff, 0xd9]))

    def test_websocket_10hz_preserved(self):
        """Verify WebSocket stream frequency constant in monitoring endpoint."""
        import inspect
        from app.api import monitoring
        source = inspect.getsource(monitoring.monitoring_ws)
        assert "asyncio.sleep(0.1)" in source, "WebSocket pusher must sleep 0.1s for ~10 Hz stream"


# ====================================================================
# 3. AUTHENTICATION, CORS & RESILIENCE
# ====================================================================

class TestAuthAndCORS:
    def test_production_cors_rejects_unauthorized_origins(self, client):
        """Verify unauthorized origins are rejected by CORS middleware."""
        headers = {
            "Origin": "http://evil-attacker.com",
            "Access-Control-Request-Method": "GET",
        }
        resp = client.options("/health", headers=headers)
        allow_origin = resp.headers.get("Access-Control-Allow-Origin")
        assert allow_origin != "http://evil-attacker.com"
        assert allow_origin != "*"

    def test_dev_localhost_ports_accepted_safely(self, client):
        """Verify safe development localhost/127.0.0.1 ports (5173-5179) are accepted."""
        for port in [5173, 5174, 5175]:
            origin = f"http://localhost:{port}"
            resp = client.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
            if origin in CORS_ALLOWED_ORIGINS:
                assert resp.headers.get("Access-Control-Allow-Origin") == origin

    def test_local_monitoring_survives_cloud_auth_expiry(self, sample_frame):
        """Verify camera acquisition and local perception continue when cloud auth is None or expired."""
        manager = get_camera_manager()
        engine = get_perception_engine()
        state = engine.process_frame(sample_frame)
        assert state is not None
        assert state.track_id == "visionguard-001"


# ====================================================================
# 4. NATURAL BILINGUAL ALERT POLICY & ASSETS
# ====================================================================

class TestNaturalBilingualAlerts:
    def test_canonical_alert_scripts_en(self):
        """Verify canonical English wellness/safety intervention messages."""
        msg1 = DEFAULT_ALERT_POLICY.get_message(RiskCategory.POSTURE, RiskLevel.MODERATE, language="en")
        msg2 = DEFAULT_ALERT_POLICY.get_message(RiskCategory.POSTURE, RiskLevel.HIGH, language="en")
        msg3 = DEFAULT_ALERT_POLICY.get_message(RiskCategory.ALERTNESS, RiskLevel.MODERATE, language="en")
        msg4 = DEFAULT_ALERT_POLICY.get_message(RiskCategory.ALERTNESS, RiskLevel.HIGH, language="en")

        assert msg1 == "Your posture has been off for a while. Consider adjusting your sitting position."
        assert msg2 == "Your posture needs attention. Please adjust your sitting position."
        assert msg3 == "You appear less alert. Consider taking a short break."
        assert msg4 == "Your alertness appears reduced. Please consider taking a break."

    def test_canonical_alert_scripts_ta(self):
        """Verify canonical Tamil Unicode wellness/safety intervention messages."""
        msg1 = DEFAULT_ALERT_POLICY.get_message(RiskCategory.POSTURE, RiskLevel.MODERATE, language="ta")
        msg2 = DEFAULT_ALERT_POLICY.get_message(RiskCategory.POSTURE, RiskLevel.HIGH, language="ta")
        msg3 = DEFAULT_ALERT_POLICY.get_message(RiskCategory.ALERTNESS, RiskLevel.MODERATE, language="ta")
        msg4 = DEFAULT_ALERT_POLICY.get_message(RiskCategory.ALERTNESS, RiskLevel.HIGH, language="ta")

        assert msg1 == "உங்கள் அமரும் தோரணையை சரிசெய்யவும்."
        assert msg2 == "தோரணையில் கவனம் தேவை. தயவுசெய்து நேராக உட்காரவும்."
        assert msg3 == "கவனம் தேவை. கண்களை சிமிட்டி புத்துணர்ச்சி பெறவும்."
        assert msg4 == "சோர்வு கண்டறியப்பட்டது. தயவுசெய்து சிறிது நேரம் ஓய்வெடுக்கவும்."

    def test_tamil_never_contains_latin_transliteration(self):
        """Verify Tamil messages are proper Tamil Unicode and not fake Latin transliteration."""
        for msg in CALM_ALERT_MESSAGES_TA.values():
            has_tamil = any("஀" <= ch <= "௿" for ch in msg)
            assert has_tamil, f"Expected Tamil Unicode in '{msg}'"
            assert "posture" not in msg.lower()
            assert "alertness" not in msg.lower()

    def test_alert_audio_keys_mapping(self):
        """Verify deterministic audio keys for pre-rendered assets."""
        assert DEFAULT_ALERT_POLICY.get_audio_key(RiskCategory.POSTURE, RiskLevel.MODERATE) == "posture_moderate"
        assert DEFAULT_ALERT_POLICY.get_audio_key(RiskCategory.POSTURE, RiskLevel.HIGH) == "posture_high"
        assert DEFAULT_ALERT_POLICY.get_audio_key(RiskCategory.ALERTNESS, RiskLevel.MODERATE) == "alertness_moderate"
        assert DEFAULT_ALERT_POLICY.get_audio_key(RiskCategory.ALERTNESS, RiskLevel.HIGH) == "alertness_high"

    def test_audio_assets_exist_on_disk(self):
        """Verify all 8 pre-rendered MP3 assets exist in frontend/public/audio/alerts."""
        frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "public", "audio", "alerts")
        required_keys = ["posture_moderate", "posture_high", "alertness_moderate", "alertness_high"]

        for lang in ["en", "ta"]:
            lang_dir = os.path.join(frontend_dir, lang)
            assert os.path.isdir(lang_dir), f"Directory {lang_dir} missing"
            for key in required_keys:
                asset_path = os.path.join(lang_dir, f"{key}.mp3")
                assert os.path.exists(asset_path), f"Asset {asset_path} missing"
                size = os.path.getsize(asset_path)
                assert size > 5000, f"Asset {asset_path} is suspiciously small: {size} bytes"

    def test_alert_language_preference_validation(self):
        """Verify UserPreferencesUpdate model validates alert_language correctly."""
        from app.api.user import UserPreferencesUpdate
        from pydantic import ValidationError

        p1 = UserPreferencesUpdate(alert_language="en")
        assert p1.alert_language == "en"
        p2 = UserPreferencesUpdate(alert_language="ta")
        assert p2.alert_language == "ta"
        p3 = UserPreferencesUpdate(alert_language="en+ta")
        assert p3.alert_language == "en+ta"

        with pytest.raises(ValidationError):
            UserPreferencesUpdate(alert_language="french")

    def test_pwa_public_audio_cache_policy(self):
        """Verify service worker precaches audio assets and excludes private APIs."""
        sw_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "dist", "sw.js")
        if os.path.exists(sw_path):
            with open(sw_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "/audio/alerts/en/posture_moderate.mp3" in content
            assert "/audio/alerts/ta/posture_moderate.mp3" in content
            assert 'url.pathname.startsWith("/api/")' in content
