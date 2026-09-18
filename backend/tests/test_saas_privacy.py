import pytest
from app.sessions.repository import (
    SupabaseSessionRepository,
    ALLOWED_SESSION_FIELDS,
    ALLOWED_RISK_EVENT_FIELDS
)

class TestPrivacyPayloadWhitelisting:
    def test_session_payload_whitelist_rejects_frames_and_landmarks(self):
        repo = SupabaseSessionRepository()
        malicious_or_leaky_payload = {
            "id": "session-1",
            "user_id": "user-1",
            "started_at": "2026-09-18T00:00:00Z",
            "duration_seconds": 120.0,
            # Leaky biometric/frame fields that must be stripped
            "frame": b"\xff\xd8\xff\xe0...",
            "jpeg_bytes": b"raw_data",
            "landmarks": [{"x": 0.5, "y": 0.5}],
            "pose_landmarks": [{"x": 0.1, "y": 0.2}],
            "face_landmarks": [{"x": 0.3, "y": 0.4}],
            "embedding": [0.123, 0.456],
            "unknown_extra_sensor_dump": "leak"
        }
        filtered = repo.filter_session_payload(malicious_or_leaky_payload)
        
        # Verify allowed keys are retained
        assert "id" in filtered
        assert "user_id" in filtered
        assert "duration_seconds" in filtered
        
        # Verify all prohibited keys are stripped
        prohibited_keys = {
            "frame", "jpeg_bytes", "landmarks", "pose_landmarks",
            "face_landmarks", "embedding", "unknown_extra_sensor_dump"
        }
        for key in prohibited_keys:
            assert key not in filtered, f"Privacy violation: {key} was not stripped from session payload!"

        # Whitelist guarantee: all keys in filtered must be in ALLOWED_SESSION_FIELDS
        for key in filtered:
            assert key in ALLOWED_SESSION_FIELDS

    def test_risk_event_payload_whitelist_rejects_frames_and_landmarks(self):
        repo = SupabaseSessionRepository()
        leaky_event_payload = {
            "id": "event-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "timestamp": "2026-09-18T00:00:00Z",
            "category": "POSTURE",
            "severity": "HIGH",
            "reason": "SLOUCH",
            "lifecycle": "STARTED",
            # Leaky fields
            "frame": b"raw_image",
            "face_crop": b"face_image",
            "biometric_hash": "abc123xyz"
        }
        filtered = repo.filter_risk_event_payload(leaky_event_payload)
        
        assert "id" in filtered
        assert "reason" in filtered
        assert "frame" not in filtered
        assert "face_crop" not in filtered
        assert "biometric_hash" not in filtered

        for key in filtered:
            assert key in ALLOWED_RISK_EVENT_FIELDS

class TestDeleteUserDataContract:
    def test_delete_user_data_terminology_and_scope(self):
        repo = SupabaseSessionRepository()
        # Ensure method is named delete_user_data (not "right to be forgotten")
        assert hasattr(repo, "delete_user_data")
        assert not hasattr(repo, "full_right_to_be_forgotten")
