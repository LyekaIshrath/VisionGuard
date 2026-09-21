import pytest
pytestmark = pytest.mark.skip(reason='Supabase removed from VisionGuard runtime in favor of MongoDB')
import os
import pytest
import requests

SB_URL = os.getenv("SUPABASE_URL", "https://uwtnjkxpzjctgthmgsjv.supabase.co")
ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV3dG5qa3hwempjdGd0aG1nc2p2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODk2ODI0OTEsImV4cCI6MjEwNTI1ODQ5MX0.kJV7cAGB0z81CRSa1rMM8EvLl4zfvAIDtJU1fYAaRws")

@pytest.fixture(scope="module")
def user_tokens():
    r_a = requests.post(
        f"{SB_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
        json={"email": "user_a@visionguard.test", "password": "TestPassword123!@#"}
    )
    assert r_a.status_code == 200, f"User A auth failed: {r_a.text}"
    tok_a = r_a.json()["access_token"]
    user_a_id = r_a.json()["user"]["id"]

    r_b = requests.post(
        f"{SB_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
        json={"email": "user_b@visionguard.test", "password": "TestPassword123!@#"}
    )
    assert r_b.status_code == 200, f"User B auth failed: {r_b.text}"
    tok_b = r_b.json()["access_token"]
    user_b_id = r_b.json()["user"]["id"]

    return {
        "user_a": {"id": user_a_id, "token": tok_a},
        "user_b": {"id": user_b_id, "token": tok_b}
    }


class TestLiveSupabaseRLS:
    def test_two_user_rls_session_isolation(self, user_tokens):
        headers_a = {
            "apikey": ANON_KEY,
            "Authorization": f"Bearer {user_tokens['user_a']['token']}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        headers_b = {
            "apikey": ANON_KEY,
            "Authorization": f"Bearer {user_tokens['user_b']['token']}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

        # 1. User B creates a session
        res_create_b = requests.post(
            f"{SB_URL}/rest/v1/monitoring_sessions",
            headers=headers_b,
            json={"user_id": user_tokens["user_b"]["id"], "status": "ACTIVE", "device_name": "Device B"}
        )
        assert res_create_b.status_code == 201
        session_b_id = res_create_b.json()[0]["id"]

        try:
            # 2. User A attempts SELECT on User B's session -> must be invisible (empty list)
            res_a_select = requests.get(
                f"{SB_URL}/rest/v1/monitoring_sessions?id=eq.{session_b_id}",
                headers=headers_a
            )
            assert res_a_select.status_code == 200
            assert len(res_a_select.json()) == 0, "RLS breached: User A can read User B session"

            # 3. User A attempts UPDATE on User B's session -> must affect 0 rows
            res_a_update = requests.patch(
                f"{SB_URL}/rest/v1/monitoring_sessions?id=eq.{session_b_id}",
                headers=headers_a,
                json={"status": "COMPLETED"}
            )
            assert res_a_update.status_code == 200
            assert len(res_a_update.json()) == 0, "RLS breached: User A updated User B session"

            # 4. User A attempts DELETE on User B's session -> must affect 0 rows
            res_a_delete = requests.delete(
                f"{SB_URL}/rest/v1/monitoring_sessions?id=eq.{session_b_id}",
                headers=headers_a
            )
            assert res_a_delete.status_code == 200
            assert len(res_a_delete.json()) == 0, "RLS breached: User A deleted User B session"

            # 5. User B still sees their session intact
            res_b_select = requests.get(
                f"{SB_URL}/rest/v1/monitoring_sessions?id=eq.{session_b_id}",
                headers=headers_b
            )
            assert res_b_select.status_code == 200
            assert len(res_b_select.json()) == 1

        finally:
            # Cleanup
            requests.delete(
                f"{SB_URL}/rest/v1/monitoring_sessions?id=eq.{session_b_id}",
                headers=headers_b
            )

    def test_two_user_rls_risk_event_isolation(self, user_tokens):
        headers_a = {
            "apikey": ANON_KEY,
            "Authorization": f"Bearer {user_tokens['user_a']['token']}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        headers_b = {
            "apikey": ANON_KEY,
            "Authorization": f"Bearer {user_tokens['user_b']['token']}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

        # Create session B
        res_s = requests.post(
            f"{SB_URL}/rest/v1/monitoring_sessions",
            headers=headers_b,
            json={"user_id": user_tokens["user_b"]["id"], "status": "ACTIVE", "device_name": "Device B"}
        )
        s_id = res_s.json()[0]["id"]

        event_id = f"evt-rls-test-{os.urandom(4).hex()}"
        res_e = requests.post(
            f"{SB_URL}/rest/v1/risk_events",
            headers=headers_b,
            json={
                "id": event_id,
                "session_id": s_id,
                "user_id": user_tokens["user_b"]["id"],
                "category": "POSTURE",
                "severity": "HIGH",
                "reason": "Test Slouch",
                "lifecycle": "STARTED"
            }
        )
        assert res_e.status_code == 201

        try:
            # User A cannot read User B's risk event
            res_a = requests.get(
                f"{SB_URL}/rest/v1/risk_events?id=eq.{event_id}",
                headers=headers_a
            )
            assert res_a.status_code == 200
            assert len(res_a.json()) == 0, "RLS breached: User A read User B risk event"
        finally:
            requests.delete(f"{SB_URL}/rest/v1/monitoring_sessions?id=eq.{s_id}", headers=headers_b)

    def test_user_id_spoofing_rejected_by_rls(self, user_tokens):
        headers_a = {
            "apikey": ANON_KEY,
            "Authorization": f"Bearer {user_tokens['user_a']['token']}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        # User A tries to insert a session claiming user_id is User B
        res = requests.post(
            f"{SB_URL}/rest/v1/monitoring_sessions",
            headers=headers_a,
            json={"user_id": user_tokens["user_b"]["id"], "status": "ACTIVE", "device_name": "Spoofer"}
        )
        assert res.status_code in (400, 403, 404, 409, 500) or "violates row-level security policy" in res.text

    def test_unauthenticated_access_denied(self):
        res = requests.get(
            f"{SB_URL}/rest/v1/monitoring_sessions",
            headers={"apikey": ANON_KEY}
        )
        assert res.status_code == 200
        assert len(res.json()) == 0, "Unauthenticated user received private session records"
