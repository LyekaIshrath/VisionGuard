import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from app.sessions.service import SessionService
from app.sessions.repository import SupabaseSessionRepository

class TestSplitBrainAndResilience:
    def test_local_monitoring_uninterrupted_when_cloud_unconfigured(self):
        with patch("app.config.config.is_cloud_configured", return_value=False):
            service = SessionService()
            local_id = service.start_session(user_id=None, token=None)
            assert local_id is not None
            assert service.cloud_session_id is None
            status_resp = service.get_cloud_status()
            assert status_resp.status == "DISABLED"
            assert status_resp.configured is False
            assert status_resp.local_session_id == local_id
            assert status_resp.cloud_session_id is None

    def test_cloud_creation_failure_does_not_break_local_session(self):
        async def run_test():
            mock_repo = SupabaseSessionRepository()
            mock_repo.create_session = AsyncMock(side_effect=Exception("Connection refused / Supabase offline"))
            mock_repo.mark_stale_sessions_interrupted = AsyncMock(return_value=0)

            with patch("app.config.config.is_cloud_configured", return_value=True):
                service = SessionService(repository=mock_repo)
                local_id = service.start_session(user_id="user-1", token="jwt-token-1")
                
                # Allow the async task to run
                await service._async_start_cloud_session(local_id, "user-1", "jwt-token-1")

                assert local_id is not None
                assert service.cloud_session_id is None
                assert service.cloud_status in ("OFFLINE", "ERROR")
                assert service.aggregator is not None  # Local session continues!

        asyncio.run(run_test())

    def test_stale_active_sessions_marked_interrupted_on_startup(self):
        async def run_test():
            mock_repo = SupabaseSessionRepository()
            mock_repo.create_session = AsyncMock(return_value={"id": "new-session", "status": "ACTIVE"})
            mock_repo.mark_stale_sessions_interrupted = AsyncMock(return_value=2)

            with patch("app.config.config.is_cloud_configured", return_value=True):
                service = SessionService(repository=mock_repo)
                local_id = service.start_session(user_id="user-1", token="jwt-token-1")
                await service._async_start_cloud_session(local_id, "user-1", "jwt-token-1")

                mock_repo.mark_stale_sessions_interrupted.assert_called_once_with(
                    user_id="user-1",
                    token="jwt-token-1",
                    current_session_id=local_id
                )
                assert service.cloud_session_id == local_id
                assert service.cloud_status == "SYNCED"

        asyncio.run(run_test())

class TestTruthfulCloudStates:
    def test_truthful_states_contract(self):
        valid_states = {"DISABLED", "SYNCING", "SYNCED", "OFFLINE", "ERROR"}
        service = SessionService()
        for state in valid_states:
            service.cloud_status = state
            with patch("app.config.config.is_cloud_configured", return_value=True):
                resp = service.get_cloud_status()
                assert resp.status in valid_states
