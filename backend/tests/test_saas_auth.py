import pytest
import time
from jose import jwt
from fastapi import HTTPException
from app.auth.token_verifier import verify_token_cryptographic
from app.auth.models import AuthenticatedUser

TEST_SECRET = "test-secret-key-32-chars-minimum-length-needed!"

@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_SECRET)

def create_token(sub="user-123", email="user@example.com", exp_offset=3600, secret=TEST_SECRET):
    payload = {
        "sub": sub,
        "email": email,
        "role": "authenticated",
        "exp": int(time.time()) + exp_offset,
        "iat": int(time.time()),
        "aud": "authenticated",
        "iss": "supabase"
    }
    return jwt.encode(payload, secret, algorithm="HS256")

class TestCryptographicAuth:
    def test_valid_token_verification(self):
        token = create_token()
        user = verify_token_cryptographic(f"Bearer {token}")
        assert isinstance(user, AuthenticatedUser)
        assert user.id == "user-123"
        assert user.email == "user@example.com"
        assert user.role == "authenticated"
        assert user.token == token

    def test_expired_token_rejected(self):
        token = create_token(exp_offset=-10)
        with pytest.raises(HTTPException) as exc_info:
            verify_token_cryptographic(token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_invalid_signature_rejected(self):
        token = create_token(secret="wrong-secret-key-that-does-not-match!")
        with pytest.raises(HTTPException) as exc_info:
            verify_token_cryptographic(token)
        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()

    def test_malformed_token_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_token_cryptographic("not.a.valid.jwt.token")
        assert exc_info.value.status_code == 401

    def test_missing_subject_rejected(self):
        payload = {
            "email": "no-sub@example.com",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, TEST_SECRET, algorithm="HS256")
        with pytest.raises(HTTPException) as exc_info:
            verify_token_cryptographic(token)
        assert exc_info.value.status_code == 401
        assert "subject" in exc_info.value.detail.lower()
