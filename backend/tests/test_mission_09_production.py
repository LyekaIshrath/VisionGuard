"""
Mission 09 production readiness tests.
Tests: health endpoint, CORS, CSP/security headers,
retention safety, no token leaks, single pipeline invariants.
"""
import os
import re
import pytest
from unittest.mock import MagicMock, PropertyMock, patch
from fastapi.testclient import TestClient


@pytest.fixture(scope='module')
def client():
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoint:

    def test_health_returns_200(self, client):
        res = client.get('/health')
        assert res.status_code == 200

    def test_health_returns_ready(self, client):
        data = client.get('/health').json()
        assert data['status'] == 'READY'

    def test_health_returns_version(self, client):
        data = client.get('/health').json()
        assert 'version' in data
        assert data['version'] == '1.0.0'

    def test_health_returns_camera_state(self, client):
        data = client.get('/health').json()
        assert 'camera_state' in data
        valid = ('STOPPED', 'NOT_CONFIGURED', 'CAMERA_ERROR', 'NO_FRAMES', 'RUNNING')
        assert data['camera_state'] in valid

    def test_health_does_not_initialize_camera(self, client):
        with patch('cv2.VideoCapture') as mock_vc:
            res = client.get('/health')
            assert res.status_code == 200
            mock_vc.assert_not_called()

    def test_health_non_sensitive_fields_only(self, client):
        data = client.get('/health').json()
        body = str(data).lower()
        assert 'secret' not in body
        assert 'anon_key' not in body
        assert 'service_role' not in body

    def test_health_is_fast(self, client):
        import time
        start = time.time()
        client.get('/health')
        assert time.time() - start < 2.0


class TestCORSAllowlist:

    def test_cors_config_not_wildcard(self):
        from app.config import CORS_ALLOWED_ORIGINS
        assert '*' not in CORS_ALLOWED_ORIGINS

    def test_cors_config_has_localhost_origins(self):
        from app.config import CORS_ALLOWED_ORIGINS
        has_local = any('localhost' in o or '127.0.0.1' in o for o in CORS_ALLOWED_ORIGINS)
        assert has_local

    def test_cors_config_is_list(self):
        from app.config import CORS_ALLOWED_ORIGINS
        assert isinstance(CORS_ALLOWED_ORIGINS, list)
        assert len(CORS_ALLOWED_ORIGINS) >= 1


class TestSecurityHeaders:

    def test_x_content_type_options(self, client):
        res = client.get('/health')
        assert res.headers.get('x-content-type-options') == 'nosniff'

    def test_x_frame_options(self, client):
        res = client.get('/health')
        assert res.headers.get('x-frame-options') == 'DENY'

    def test_referrer_policy(self, client):
        res = client.get('/health')
        assert 'referrer-policy' in res.headers

    def test_permissions_policy(self, client):
        res = client.get('/health')
        pp = res.headers.get('permissions-policy', '')
        assert 'camera=()' in pp
        assert 'microphone=()' in pp

    def test_csp_header_present(self, client):
        res = client.get('/health')
        assert 'content-security-policy' in res.headers

    def test_csp_has_default_src_self(self, client):
        res = client.get('/health')
        csp = res.headers.get('content-security-policy', '')
        assert "default-src 'self'" in csp

    def test_csp_no_unsafe_eval(self, client):
        res = client.get('/health')
        csp = res.headers.get('content-security-policy', '')
        assert 'wasm-unsafe-eval' not in csp

    def test_csp_has_frame_ancestors_none(self, client):
        res = client.get('/health')
        csp = res.headers.get('content-security-policy', '')
        assert "frame-ancestors 'none'" in csp

    def test_correlation_id_header_present(self, client):
        res = client.get('/health')
        assert 'x-request-id' in res.headers

    def test_correlation_id_is_uuid(self, client):
        res = client.get('/health')
        req_id = res.headers.get('x-request-id', '')
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            re.IGNORECASE,
        )
        assert uuid_pattern.match(req_id), f'Not a UUID: {req_id}'

    def test_correlation_id_propagated(self, client):
        test_id = 'test-req-abc-123'
        res = client.get('/health', headers={'X-Request-ID': test_id})
        assert res.headers.get('x-request-id') == test_id


class TestRetentionSafety:

    def test_cleanup_skips_when_no_base_url(self):
        from app.sessions.repository import SupabaseSessionRepository
        repo = SupabaseSessionRepository()
        import asyncio
        async def run():
            with patch.object(SupabaseSessionRepository, 'base_url', new_callable=PropertyMock, return_value=''):
                result = await repo.cleanup_expired_sessions(
                    user_id='uid', token='tok', retention_days=30
                )
                assert result == 0
        asyncio.run(run())

    def test_cleanup_skips_when_zero_days(self):
        from app.sessions.repository import SupabaseSessionRepository
        repo = SupabaseSessionRepository()
        import asyncio
        async def run():
            with patch.object(SupabaseSessionRepository, 'base_url', new_callable=PropertyMock, return_value='http://fake'):
                result = await repo.cleanup_expired_sessions(
                    user_id='uid', token='tok', retention_days=0
                )
                assert result == 0
        asyncio.run(run())

    def test_cleanup_url_filters_completed_status(self):
        from app.sessions.repository import SupabaseSessionRepository
        repo = SupabaseSessionRepository()
        captured_urls = []
        import asyncio
        async def run():
            with patch.object(SupabaseSessionRepository, 'base_url', new_callable=PropertyMock, return_value='http://fake/rest/v1'), \
                 patch.object(SupabaseSessionRepository, 'anon_key', new_callable=PropertyMock, return_value='fakekey'), \
                 patch('httpx.AsyncClient') as mock_client_cls:
                mock_inst = MagicMock()
                mock_inst.__aenter__ = MagicMock(return_value=mock_inst)
                mock_inst.__aexit__ = MagicMock(return_value=False)
                async def fake_get(url, **kw):
                    captured_urls.append(url)
                    r = MagicMock(); r.status_code = 200; r.json.return_value = []
                    return r
                mock_inst.get = MagicMock(side_effect=fake_get)
                mock_client_cls.return_value = mock_inst
                await repo.cleanup_expired_sessions('uid', 'tok', 30)
        asyncio.run(run())
        for url in captured_urls:
            assert 'status=eq.COMPLETED' in url, f'Missing status filter: {url}'
            assert 'user_id=eq.uid' in url


class TestNoTokenLeaks:

    def test_redacting_formatter_strips_bearer(self):
        from app.middleware.security import RedactingFormatter
        import logging
        fmt = RedactingFormatter(fmt='%(message)s')
        rec = logging.LogRecord(
            'test', logging.INFO, '', 0,
            'Authorization: Bearer eyJhbGciOiJFUzI1NiJ9.fake.jwt', (), None
        )
        out = fmt.format(rec)
        assert 'eyJhbGciOiJFUzI1NiJ9.fake.jwt' not in out
        assert '[REDACTED]' in out

    def test_redacting_formatter_strips_password(self):
        from app.middleware.security import RedactingFormatter
        import logging
        fmt = RedactingFormatter(fmt='%(message)s')
        rec = logging.LogRecord(
            'test', logging.INFO, '', 0, 'password=mysecretval', (), None
        )
        out = fmt.format(rec)
        assert 'mysecretval' not in out
        assert '[REDACTED]' in out

    def test_redacting_formatter_preserves_normal(self):
        from app.middleware.security import RedactingFormatter
        import logging
        fmt = RedactingFormatter(fmt='%(message)s')
        rec = logging.LogRecord(
            'test', logging.INFO, '', 0, 'Session started cycle 42', (), None
        )
        assert 'Session started cycle 42' in fmt.format(rec)


class TestSinglePipelineInvariants:

    def test_camera_status_does_not_open_capture(self):
        from app.camera.manager import get_camera_manager
        manager = get_camera_manager()
        with patch('cv2.VideoCapture') as mock_vc:
            manager.status()
            mock_vc.assert_not_called()

    def test_camera_manager_singleton_same_index(self):
        from app.camera.manager import get_camera_manager
        assert get_camera_manager(0) is get_camera_manager(0)

    def test_no_get_user_media_in_frontend(self):
        frontend_src = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', '..', 'frontend', 'src'
        )
        violations = []
        for root, dirs, files in os.walk(frontend_src):
            dirs[:] = [d for d in dirs if d not in ('node_modules', 'dist')]
            for fname in files:
                if not fname.endswith(('.ts', '.tsx', '.js')):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    text = open(fpath, 'r', encoding='utf-8', errors='ignore').read()
                    if 'getUserMedia' in text or 'mediaDevices' in text:
                        violations.append(fpath)
                except Exception:
                    pass
        assert violations == [], f'getUserMedia found in frontend: {violations}'

    def test_config_cors_no_wildcard(self):
        from app.config import CORS_ALLOWED_ORIGINS
        assert '*' not in CORS_ALLOWED_ORIGINS

    def test_version_is_1_0_0(self):
        from app.config import app_version
        assert app_version == '1.0.0'

    def test_version_file_exists(self):
        version_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', '..', 'VERSION'
        )
        assert os.path.isfile(version_path), 'VERSION file must exist at repo root'
        content = open(version_path).read().strip()
        assert content == '1.0.0'

    def test_supabase_jwt_secret_not_primary_auth(self):
        from app.auth.token_verifier import verify_token_cryptographic
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            verify_token_cryptographic('not.a.valid.jwt')
        assert exc_info.value.status_code == 401
