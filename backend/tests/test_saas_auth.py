import pytest
import time
from jose import jwt, jwk
from fastapi import HTTPException
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

from app.auth.token_verifier import verify_token_cryptographic, _jwks_cache
from app.auth.models import AuthenticatedUser

TEST_SECRET = "test-secret-key-32-chars-minimum-length-needed!"
TEST_SB_URL = "https://test-project.supabase.co"


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("SUPABASE_URL", TEST_SB_URL)
    _jwks_cache.clear()


def create_hs256_token(sub="user-123", email="user@example.com", exp_offset=3600, secret=TEST_SECRET):
    payload = {
        "sub": sub,
        "email": email,
        "role": "authenticated",
        "exp": int(time.time()) + exp_offset,
        "iat": int(time.time()),
        "aud": "authenticated",
        "iss": "supabase",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def ec_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = private_key.public_key()
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    jwk_dict = jwk.construct(pem_public, "ES256").to_dict()
    jwk_dict["kid"] = "test-ec-kid-1"
    jwk_dict["alg"] = "ES256"
    return pem_private.decode("utf-8"), jwk_dict


class TestCryptographicAuth:
    def test_valid_token_verification_hs256(self):
        token = create_hs256_token()
        user = verify_token_cryptographic(f"Bearer {token}")
        assert isinstance(user, AuthenticatedUser)
        assert user.id == "user-123"
        assert user.email == "user@example.com"
        assert user.role == "authenticated"
        assert user.token == token

    def test_expired_token_rejected_hs256(self):
        token = create_hs256_token(exp_offset=-10)
        with pytest.raises(HTTPException) as exc_info:
            verify_token_cryptographic(token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_invalid_signature_rejected_hs256(self):
        token = create_hs256_token(secret="wrong-secret-key-that-does-not-match!")
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

    def test_valid_es256_jwks_verification(self, ec_keypair):
        pem_private, jwk_dict = ec_keypair
        # Preload JWKS cache
        _jwks_cache[jwk_dict["kid"]] = jwk_dict

        payload = {
            "sub": "ec-user-555",
            "email": "ec.user@visionguard.test",
            "role": "authenticated",
            "aud": "authenticated",
            "iss": f"{TEST_SB_URL}/auth/v1",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        }
        token = jwt.encode(payload, pem_private, algorithm="ES256", headers={"kid": jwk_dict["kid"]})
        user = verify_token_cryptographic(token)
        assert user.id == "ec-user-555"
        assert user.email == "ec.user@visionguard.test"
        assert user.role == "authenticated"

    def test_es256_tampered_signature_rejected(self, ec_keypair):
        pem_private, jwk_dict = ec_keypair
        _jwks_cache[jwk_dict["kid"]] = jwk_dict

        payload = {
            "sub": "ec-user-555",
            "email": "ec.user@visionguard.test",
            "role": "authenticated",
            "aud": "authenticated",
            "iss": f"{TEST_SB_URL}/auth/v1",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, pem_private, algorithm="ES256", headers={"kid": jwk_dict["kid"]})
        parts = token.split(".")
        tampered = parts[0] + ".eyJuYW1lIjoiSGFjayJ9." + parts[2]
        with pytest.raises(HTTPException) as exc_info:
            verify_token_cryptographic(tampered)
        assert exc_info.value.status_code == 401

    def test_es256_audience_mismatch_rejected(self, ec_keypair):
        pem_private, jwk_dict = ec_keypair
        _jwks_cache[jwk_dict["kid"]] = jwk_dict

        payload = {
            "sub": "ec-user-555",
            "email": "ec.user@visionguard.test",
            "aud": "wrong-audience",
            "iss": f"{TEST_SB_URL}/auth/v1",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, pem_private, algorithm="ES256", headers={"kid": jwk_dict["kid"]})
        with pytest.raises(HTTPException) as exc_info:
            verify_token_cryptographic(token)
        assert exc_info.value.status_code == 401

    def test_es256_issuer_mismatch_rejected(self, ec_keypair):
        pem_private, jwk_dict = ec_keypair
        _jwks_cache[jwk_dict["kid"]] = jwk_dict

        payload = {
            "sub": "ec-user-555",
            "email": "ec.user@visionguard.test",
            "aud": "authenticated",
            "iss": "https://attacker-idp.com/auth/v1",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, pem_private, algorithm="ES256", headers={"kid": jwk_dict["kid"]})
        with pytest.raises(HTTPException) as exc_info:
            verify_token_cryptographic(token)
        assert exc_info.value.status_code == 401

    def test_es256_expired_rejected(self, ec_keypair):
        pem_private, jwk_dict = ec_keypair
        _jwks_cache[jwk_dict["kid"]] = jwk_dict

        payload = {
            "sub": "ec-user-555",
            "email": "ec.user@visionguard.test",
            "aud": "authenticated",
            "iss": f"{TEST_SB_URL}/auth/v1",
            "exp": int(time.time()) - 60,
        }
        token = jwt.encode(payload, pem_private, algorithm="ES256", headers={"kid": jwk_dict["kid"]})
        with pytest.raises(HTTPException) as exc_info:
            verify_token_cryptographic(token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()
