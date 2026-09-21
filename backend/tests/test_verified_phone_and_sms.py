"""Comprehensive regression tests for VisionGuard Verified Phone & SMS Alert System.

Verifies:
1. Phone normalization (canonical E.164 format)
2. Invalid phone number rejection
3. Duplicate verified phone protection
4. OTP expiration handling
5. Wrong OTP rejection
6. Verification attempt limits (max 3 attempts -> LOCKED)
7. Resend cooldown enforcement
8. Per-phone hourly rate limiting
9. Successful end-to-end registration flow (start -> verify -> active verified user)
10. Unverified phone cannot receive safety alerts
11. SMS user preference OFF suppression
12. SMS event category filtering (posture, alertness, away, session)
13. SMS alert cooldown enforcement (120 seconds)
14. Cross-user security and isolation
15. Test SMS endpoint security (never accepts arbitrary destination from request body)
16. Strict privacy whitelist (text-only alerts, zero biometric/telemetry payload)
"""

import time
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.db.mongodb import mongo_repository, UserRepository
from app.notifications.phone_utils import normalize_phone_number, mask_phone_number
from app.notifications.sms_provider import (
    ApplicationManagedSmsProvider,
    OTP_EXPIRATION_SECONDS,
    OTP_MAX_ATTEMPTS,
    OTP_RESEND_COOLDOWN_SECONDS,
    MAX_VERIFICATIONS_PER_HOUR,
    sms_provider,
)
from app.alerts.sms_notification_provider import SmsNotificationProvider
from jose import jwt


TEST_JWT_SECRET = "test-secret-key-32-chars-minimum-length-needed!"
client = TestClient(app)


def make_token(user_id: str, email: str = "test@example.com") -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": "authenticated",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "aud": "authenticated",
        "iss": "supabase",
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


def gen_phone() -> str:
    return f"+9198{uuid.uuid4().int % 100000000:08d}"


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")


class TestPhoneNormalizationAndMasking:
    """1 & 2: Phone normalization and masking validations."""

    def test_valid_e164_normalization(self):
        # Indian standard
        assert normalize_phone_number("+919876543210") == "+919876543210"
        assert normalize_phone_number("9876543210", default_country_code="+91") == "+919876543210"
        assert normalize_phone_number("+91 98765-43210") == "+919876543210"

        # US standard
        assert normalize_phone_number("+1 (555) 234-5678") == "+15552345678"
        assert normalize_phone_number("5552345678", default_country_code="+1") == "+15552345678"

        # UK standard
        assert normalize_phone_number("+44 7911 123456") == "+447911123456"

    def test_invalid_phone_rejection(self):
        with pytest.raises(ValueError, match="Invalid phone number"):
            normalize_phone_number("123")

        with pytest.raises(ValueError, match="Invalid phone number"):
            normalize_phone_number("+919876543210000000000")

        with pytest.raises(ValueError, match="Invalid phone number"):
            normalize_phone_number("not-a-number")

        with pytest.raises(ValueError, match="Invalid phone number"):
            normalize_phone_number("")

    def test_phone_masking(self):
        assert mask_phone_number("+919876543210") == "+91 ******3210"
        assert mask_phone_number("+15552345678") == "+1 ******5678"
        assert mask_phone_number("") == ""


class TestOtpProviderSecurity:
    """3 to 8: OTP security lifecycle, hashing, attempt limits, expiration."""

    def test_plaintext_otp_never_stored_in_mongo(self):
        provider = ApplicationManagedSmsProvider()
        test_phone = gen_phone()
        res = provider.send_verification(test_phone)

        assert res["status"] == "OTP_SENT"
        assert "phone_number_masked" in res

        db = mongo_repository.client.db
        rec = db.phone_verifications.find_one({"phone_number": test_phone, "status": "PENDING"})
        assert rec is not None
        assert "code_hash" in rec
        assert "salt" in rec
        assert "code" not in rec
        assert "raw_code" not in rec

    def test_wrong_otp_and_attempt_limit_lockout(self):
        provider = ApplicationManagedSmsProvider()
        test_phone = gen_phone()
        provider.send_verification(test_phone)

        # Attempt 1
        with pytest.raises(ValueError, match=r"Invalid verification code"):
            provider.verify_code(test_phone, "000000")

        # Attempt 2
        with pytest.raises(ValueError, match=r"Invalid verification code"):
            provider.verify_code(test_phone, "000000")

        # Attempt 3 -> Lockout
        with pytest.raises(ValueError, match=r"Too many incorrect attempts"):
            provider.verify_code(test_phone, "000000")

        # Subsequent attempts remain locked
        with pytest.raises(ValueError, match=r"Too many incorrect attempts"):
            provider.verify_code(test_phone, "000000")

    def test_otp_expiration(self):
        provider = ApplicationManagedSmsProvider()
        test_phone = gen_phone()
        provider.send_verification(test_phone)

        raw_code = provider._last_test_code["code"]
        db = mongo_repository.client.db

        db.phone_verifications.update_one(
            {"phone_number": test_phone, "status": "PENDING"},
            {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=10)}},
        )

        with pytest.raises(ValueError, match="Verification code has expired"):
            provider.verify_code(test_phone, raw_code)

    def test_resend_cooldown(self):
        provider = ApplicationManagedSmsProvider()
        test_phone = gen_phone()
        provider.send_verification(test_phone)

        with pytest.raises(ValueError, match=r"Please wait .* seconds before requesting a new verification code"):
            provider.send_verification(test_phone)

    def test_hourly_rate_limit(self):
        provider = ApplicationManagedSmsProvider()
        test_phone = gen_phone()
        db = mongo_repository.client.db

        now = datetime.now(timezone.utc)
        for _ in range(MAX_VERIFICATIONS_PER_HOUR):
            db.phone_verifications.insert_one({
                "phone_number": test_phone,
                "created_at": now - timedelta(minutes=10),
                "verified": False,
                "status": "SUPERSEDED",
            })

        with pytest.raises(ValueError, match="Too many verification attempts for this phone number"):
            provider.send_verification(test_phone)


class TestRegistrationAndPhoneLifecycleEndpoints:
    """9 & 10: End-to-end registration flow and duplicate phone constraints."""

    def test_successful_registration_with_phone_verification(self):
        unique_id = uuid.uuid4().hex[:6]
        phone = gen_phone()
        email = f"user_{unique_id}@example.com"
        password = "SecurePassword123!"

        # 1. Start registration
        start_payload = {
            "name": f"Test User {unique_id}",
            "email": email,
            "phone_number": phone,
            "password": password,
            "confirm_password": password,
        }
        res = client.post("/api/v1/auth/register/start", json=start_payload)
        assert res.status_code == 200, res.text
        start_data = res.json()
        assert start_data["status"] == "OTP_SENT"
        assert "phone_number_masked" in start_data

        # 2. Wrong OTP fails
        verify_fail = client.post("/api/v1/auth/register/verify", json={"phone_number": phone, "code": "000000"})
        assert verify_fail.status_code == 400

        # 3. Retrieve valid OTP from provider test hook
        from app.notifications.sms_provider import sms_provider
        otp_code = sms_provider._last_test_code["code"]

        # 4. Correct OTP creates account
        verify_success = client.post("/api/v1/auth/register/verify", json={"phone_number": phone, "code": otp_code})
        assert verify_success.status_code == 201, verify_success.text
        user_res = verify_success.json()
        assert user_res["user"]["email"] == email
        assert user_res["user"]["phone_verified"] is True
        assert "access_token" in user_res
        user_id = user_res["user"]["id"]

        # 5. Verify DB state directly
        db = mongo_repository.client.db
        user_doc = db.users.find_one({"_id": user_id})
        assert user_doc is not None
        assert user_doc["phone_number"] == phone
        assert user_doc["phone_verified"] is True
        assert user_doc["phone_verified_at"] is not None

    def test_duplicate_verified_phone_rejection(self):
        unique_id = uuid.uuid4().hex[:6]
        phone = gen_phone()
        email1 = f"user1_{unique_id}@example.com"
        email2 = f"user2_{unique_id}@example.com"

        user_repo = UserRepository()
        user1 = user_repo.create_user(
            email=email1,
            password_hash="fakehash",
            phone_number=phone,
            phone_verified=True,
            phone_verified_at=datetime.now(timezone.utc),
        )
        assert user1["phone_verified"] is True

        res = client.post("/api/v1/auth/register/start", json={
            "name": "User Two",
            "email": email2,
            "phone_number": phone,
            "password": "Password123!",
            "confirm_password": "Password123!",
        })
        assert res.status_code in (400, 409)
        assert "already registered and verified" in res.json()["detail"]


class TestSmsAlertPolicyAndOrchestration:
    """11, 12, 13: Alert policy, preferences, filters, cooldown, and privacy."""

    def test_unverified_phone_cannot_receive_sms_alerts(self):
        user_repo = UserRepository()
        user = user_repo.create_user(
            email=f"unverified_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="fakehash",
            phone_number=gen_phone(),
            phone_verified=False,
        )
        provider = SmsNotificationProvider(cooldown_seconds=60)
        res = provider.send_alert_if_eligible(
            user_id=user["id"],
            event_type="POSTURE_RISK_SUSTAINED",
            severity="HIGH",
            title="Posture Risk",
            message="Sustained forward lean detected.",
        )
        assert res["status"] == "SKIPPED"
        assert res["reason"] == "PHONE_NOT_VERIFIED"

    def test_sms_preference_disabled_suppresses_alert(self):
        user_repo = UserRepository()
        user = user_repo.create_user(
            email=f"pref_off_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="fakehash",
            phone_number=gen_phone(),
            phone_verified=True,
            phone_verified_at=datetime.now(timezone.utc),
        )
        mongo_repository.preferences.update_user_preferences(user_id=user["id"], payload={"sms_alerts_enabled": False})

        provider = SmsNotificationProvider(cooldown_seconds=60)
        res = provider.send_alert_if_eligible(
            user_id=user["id"],
            event_type="POSTURE_RISK_SUSTAINED",
            severity="HIGH",
            title="Posture Risk",
            message="Sustained forward lean.",
        )
        assert res["status"] == "SKIPPED"
        assert res["reason"] == "SMS_PREFERENCE_DISABLED"

    def test_event_category_filtering(self):
        user_repo = UserRepository()
        user = user_repo.create_user(
            email=f"filter_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="fakehash",
            phone_number=gen_phone(),
            phone_verified=True,
            phone_verified_at=datetime.now(timezone.utc),
        )
        mongo_repository.preferences.update_user_preferences(user_id=user["id"], payload={
            "sms_alerts_enabled": True,
            "notify_posture": False,
            "notify_alertness": True,
        })

        provider = SmsNotificationProvider(cooldown_seconds=120)

        res_posture = provider.send_alert_if_eligible(
            user_id=user["id"],
            event_type="POSTURE_RISK_SUSTAINED",
            severity="HIGH",
            title="Posture Risk",
            message="Forward lean.",
        )
        assert res_posture["status"] == "SKIPPED"
        assert res_posture["reason"] == "POSTURE_ALERTS_FILTERED"

        res_alertness = provider.send_alert_if_eligible(
            user_id=user["id"],
            event_type="ALERTNESS_RISK_HIGH",
            severity="CRITICAL",
            title="Drowsiness Risk",
            message="High drowsiness detected.",
        )
        assert res_alertness["status"] == "DELIVERED"

    def test_sms_cooldown_enforcement(self):
        user_repo = UserRepository()
        user = user_repo.create_user(
            email=f"cd_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="fakehash",
            phone_number=gen_phone(),
            phone_verified=True,
            phone_verified_at=datetime.now(timezone.utc),
        )
        provider = SmsNotificationProvider(cooldown_seconds=120)

        t0 = 1000.0
        res1 = provider.send_alert_if_eligible(
            user_id=user["id"],
            event_type="ALERTNESS_RISK_HIGH",
            severity="CRITICAL",
            title="Drowsiness Alert",
            message="Microsleep risk.",
            current_mono=t0,
        )
        assert res1["status"] == "DELIVERED"

        res2 = provider.send_alert_if_eligible(
            user_id=user["id"],
            event_type="ALERTNESS_RISK_HIGH",
            severity="CRITICAL",
            title="Drowsiness Alert",
            message="Microsleep risk.",
            current_mono=t0 + 30.0,
        )
        assert res2["status"] == "SKIPPED"
        assert res2["reason"] == "COOLDOWN_ACTIVE"
        assert res2["remaining_seconds"] == 90

        res3 = provider.send_alert_if_eligible(
            user_id=user["id"],
            event_type="ALERTNESS_RISK_HIGH",
            severity="CRITICAL",
            title="Drowsiness Alert",
            message="Microsleep risk.",
            current_mono=t0 + 121.0,
        )
        assert res3["status"] == "DELIVERED"


class TestCrossUserIsolationAndTestSmsEndpoint:
    """14, 15, 16: Security isolation, arbitrary destination denial, privacy payload."""

    def test_test_sms_endpoint_security_and_arbitrary_destination_denial(self):
        user_repo = UserRepository()
        phone = gen_phone()
        user = user_repo.create_user(
            email=f"security_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="fakehash",
            phone_number=phone,
            phone_verified=True,
            phone_verified_at=datetime.now(timezone.utc),
        )
        token = make_token(user["id"], user["email"])

        arbitrary_phone = "+19998887777"
        res = client.post(
            "/api/v1/notifications/test-sms",
            headers={"Authorization": f"Bearer {token}"},
            json={"phone_number": arbitrary_phone, "message": "Spam attack"},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "DELIVERED"
        assert data["delivery_summary"]["recipient"] == mask_phone_number(phone)
        assert arbitrary_phone not in str(data)

    def test_test_sms_fails_for_unverified_user(self):
        user_repo = UserRepository()
        user = user_repo.create_user(
            email=f"unver_test_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="fakehash",
            phone_number=gen_phone(),
            phone_verified=False,
        )
        token = make_token(user["id"], user["email"])

        res = client.post(
            "/api/v1/notifications/test-sms",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code in (400, 409)
        assert "No verified phone number found" in res.json()["detail"]

    def test_privacy_payload_contains_no_sensitive_biometrics(self):
        """Verify SMS messages never contain landmarks, raw telemetry, or camera feeds."""
        user_repo = UserRepository()
        user = user_repo.create_user(
            email=f"privacy_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="fakehash",
            phone_number=gen_phone(),
            phone_verified=True,
            phone_verified_at=datetime.now(timezone.utc),
        )
        captured_messages = []

        with patch("app.notifications.sms_provider.ApplicationManagedSmsProvider.send_alert", side_effect=lambda phone, msg: captured_messages.append(msg) or True):
            provider = SmsNotificationProvider()
            provider.send_alert_if_eligible(
                user_id=user["id"],
                event_type="POSTURE_RISK_SUSTAINED",
                severity="HIGH",
                title="Posture Risk",
                message="Sustained forward lean detected.",
            )

        assert len(captured_messages) == 1
        msg = captured_messages[0]
        forbidden = ["face_landmarks", "pose_landmarks", "eye_closure", "keyboard", "mouse", "screen", "telemetry", "base64", "image"]
        for word in forbidden:
            assert word not in msg.lower(), f"Forbidden word '{word}' found in SMS text!"

        assert "VisionGuard Alert:" in msg
        assert "Posture Risk" in msg
