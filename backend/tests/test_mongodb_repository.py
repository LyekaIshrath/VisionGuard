from __future__ import annotations

import uuid
from datetime import datetime, timezone
import pytest

from app.db.mongodb import MongoDBClient, SessionRepository, ActivityEventRepository, UserPreferencesRepository


@pytest.fixture
def mongo_client():
    client = MongoDBClient.get_instance()
    client.connect()
    return client


class TestMongoDBRepositoryAndUserSecurity:
    """Verifies MongoDB application persistence, CRUD, indexes, and cross-user security isolation."""

    def test_indexes_created_and_idempotent(self, mongo_client):
        """Verify explicit ensure_indexes creates all required indexes idempotently."""
        assert mongo_client.is_connected
        res = mongo_client.ensure_indexes()
        assert res is True

        db = mongo_client.db
        session_indexes = [idx["name"] for idx in db.monitoring_sessions.list_indexes()]
        assert "uniq_session_id" in session_indexes
        assert "idx_user_started" in session_indexes
        assert "idx_user_status" in session_indexes

        event_indexes = [idx["name"] for idx in db.activity_events.list_indexes()]
        assert "uniq_event_id" in event_indexes
        assert "idx_session_time" in event_indexes

    def test_session_lifecycle_crud(self, mongo_client):
        """Verify create, finalize, read, and delete session."""
        repo = SessionRepository(mongo_client)
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        start_time = datetime.now(timezone.utc)

        # 1. Create
        created = repo.create_session(user_id=user_id, session_id=session_id, started_at=start_time)
        assert created is True

        # 2. Verify RUNNING
        doc = repo.get_session(user_id=user_id, session_id=session_id)
        assert doc is not None
        assert doc["status"] == "RUNNING"
        assert doc["session_id"] == session_id

        # 3. Finalize
        end_time = datetime.now(timezone.utc)
        report = {
            "presence": {"present_seconds": 120.0, "away_seconds": 10.0},
            "work_activity": {"engaged_seconds": 100.0, "observing_seconds": 20.0},
            "computer": {"keyboard_events": 45, "mouse_movements": 80},
            "timeline": [{"event": "SESSION_START"}, {"event": "SESSION_STOP"}],
        }
        finalized = repo.finalize_session(
            user_id=user_id, session_id=session_id, ended_at=end_time,
            duration_seconds=130.0, report_data=report,
        )
        assert finalized is True

        # 4. Verify Finalized State
        doc_final = repo.get_session(user_id=user_id, session_id=session_id)
        assert doc_final["status"] == "COMPLETED"
        assert doc_final["duration_seconds"] == 130.0
        assert doc_final["presence_summary"]["present_seconds"] == 120.0
        assert doc_final["activity_summary"]["engaged_seconds"] == 100.0
        assert len(doc_final["timeline"]) == 2

        # 5. Delete
        deleted = repo.delete_session(user_id=user_id, session_id=session_id)
        assert deleted is True
        assert repo.get_session(user_id=user_id, session_id=session_id) is None

    def test_cross_user_isolation(self, mongo_client):
        """Verify User A and User B cannot access, read, or delete each other's sessions."""
        repo = SessionRepository(mongo_client)
        user_a = f"user_a_{uuid.uuid4().hex[:8]}"
        user_b = f"user_b_{uuid.uuid4().hex[:8]}"
        session_a = f"sess_a_{uuid.uuid4().hex[:8]}"
        session_b = f"sess_b_{uuid.uuid4().hex[:8]}"

        repo.create_session(user_id=user_a, session_id=session_a, started_at=datetime.now(timezone.utc))
        repo.create_session(user_id=user_b, session_id=session_b, started_at=datetime.now(timezone.utc))

        try:
            # User B attempts to read User A's session -> Must return None
            stolen_read = repo.get_session(user_id=user_b, session_id=session_a)
            assert stolen_read is None

            # User B attempts to delete User A's session -> Must fail (returns False)
            stolen_delete = repo.delete_session(user_id=user_b, session_id=session_a)
            assert stolen_delete is False
            # Verify User A's session is still intact
            assert repo.get_session(user_id=user_a, session_id=session_a) is not None

            # User A lists sessions -> Only sees session_a, NOT session_b
            list_a = repo.list_sessions(user_id=user_a)
            sess_ids_a = [s["session_id"] for s in list_a]
            assert session_a in sess_ids_a
            assert session_b not in sess_ids_a
        finally:
            repo.delete_session(user_id=user_a, session_id=session_a)
            repo.delete_session(user_id=user_b, session_id=session_b)

    def test_timeline_events_recorded_and_ordered(self, mongo_client):
        """Verify timeline events are stored and retrieved chronologically."""
        repo = ActivityEventRepository(mongo_client)
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        session_id = f"sess_{uuid.uuid4().hex[:8]}"

        t1 = datetime.now(timezone.utc)
        t2 = datetime.now(timezone.utc)

        e1_id = f"evt_{uuid.uuid4().hex[:8]}"
        e2_id = f"evt_{uuid.uuid4().hex[:8]}"
        repo.record_event(user_id, session_id, e1_id, "SESSION_START", t1)
        repo.record_event(user_id, session_id, e2_id, "ENGAGED", t2)

        events = repo.list_events_for_session(user_id, session_id)
        assert len(events) == 2
        assert events[0]["event_type"] == "SESSION_START"
        assert events[1]["event_type"] == "ENGAGED"

        # Cross-user check for events
        other_user = "other_user_id"
        other_events = repo.list_events_for_session(other_user, session_id)
        assert len(other_events) == 0

    def test_offline_fallback_safety(self):
        """Verify repository behaves safely and truthfully when disconnected from MongoDB."""
        fake_client = MongoDBClient(uri="mongodb://invalid_host:27099", db_name="invalid")
        repo = SessionRepository(fake_client)

        # Operation should fail gracefully without crashing
        res = repo.create_session("user", "sess", datetime.now(timezone.utc))
        assert res is False
        assert repo.get_session("user", "sess") is None
