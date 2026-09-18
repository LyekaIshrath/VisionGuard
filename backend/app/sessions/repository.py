import os
import httpx
from typing import Optional, Dict, Any, List
from app.config import config

# Strict field whitelists to ensure no raw frames, landmarks, or biometric vectors leak
ALLOWED_SESSION_FIELDS = {
    "id", "user_id", "started_at", "ended_at", "duration_seconds",
    "good_posture_seconds", "posture_risk_seconds", "alertness_risk_seconds",
    "average_posture_score", "average_alertness_score", "risk_event_count",
    "intervention_count", "valid_posture_seconds", "valid_alertness_seconds",
    "status", "device_name"
}

ALLOWED_RISK_EVENT_FIELDS = {
    "id", "session_id", "user_id", "timestamp", "category",
    "severity", "reason", "lifecycle", "duration_seconds", "metadata"
}

ALLOWED_USER_PREFERENCE_FIELDS = {
    "user_id", "browser_notifications_enabled", "data_retention_days",
    "voice_alerts_enabled", "voice_volume", "voice_rate", "voice_pitch",
    "quiet_mode_enabled", "selected_voice", "timezone"
}

ALLOWED_PERSONAL_GOAL_FIELDS = {
    "id", "user_id", "goal_type", "target_value", "created_at", "updated_at"
}


class SupabaseSessionRepository:
    """
    Communicates with Supabase / PostgREST using the authenticated user's JWT.
    Enforces Row-Level Security (RLS) on all user operations.
    """
    @property
    def base_url(self) -> str:
        sb_url = os.getenv("SUPABASE_URL") or config.SUPABASE_URL or ""
        return f"{sb_url.rstrip('/')}/rest/v1" if sb_url else ""

    @property
    def anon_key(self) -> str:
        return os.getenv("SUPABASE_ANON_KEY") or config.SUPABASE_ANON_KEY or ""

    def _get_headers(self, token: str, prefer_return: bool = True, upsert: bool = False) -> Dict[str, str]:
        headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        prefer_vals = []
        if prefer_return:
            prefer_vals.append("return=representation")
        if upsert:
            prefer_vals.append("resolution=merge-duplicates")
        if prefer_vals:
            headers["Prefer"] = ", ".join(prefer_vals)
        return headers

    def filter_session_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if k in ALLOWED_SESSION_FIELDS}

    def filter_risk_event_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if k in ALLOWED_RISK_EVENT_FIELDS}

    def filter_preference_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if k in ALLOWED_USER_PREFERENCE_FIELDS}

    def filter_goal_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if k in ALLOWED_PERSONAL_GOAL_FIELDS}

    async def create_session(self, token: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        clean_data = self.filter_session_payload(payload)
        url = f"{self.base_url}/monitoring_sessions"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, headers=self._get_headers(token), json=clean_data)
            if resp.status_code in (200, 201):
                results = resp.json()
                return results[0] if results else None
            resp.raise_for_status()

    async def update_session(self, session_id: str, token: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        clean_data = self.filter_session_payload(payload)
        url = f"{self.base_url}/monitoring_sessions?id=eq.{session_id}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.patch(url, headers=self._get_headers(token), json=clean_data)
            if resp.status_code in (200, 204):
                if resp.status_code == 200:
                    results = resp.json()
                    return results[0] if results else None
                return clean_data
            resp.raise_for_status()

    async def get_session(self, session_id: str, token: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/monitoring_sessions?id=eq.{session_id}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=self._get_headers(token))
            if resp.status_code == 200:
                results = resp.json()
                return results[0] if results else None
            resp.raise_for_status()

    async def list_sessions(self, token: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/monitoring_sessions?order=started_at.desc&limit={limit}&offset={offset}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=self._get_headers(token))
            if resp.status_code == 200:
                return resp.json()
            resp.raise_for_status()

    async def upsert_risk_event(self, token: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        clean_data = self.filter_risk_event_payload(payload)
        url = f"{self.base_url}/risk_events"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                url, 
                headers=self._get_headers(token, prefer_return=True, upsert=True), 
                json=clean_data
            )
            if resp.status_code in (200, 201):
                results = resp.json()
                return results[0] if results else clean_data
            resp.raise_for_status()

    async def get_session_events(self, session_id: str, token: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/risk_events?session_id=eq.{session_id}&order=timestamp.asc"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=self._get_headers(token))
            if resp.status_code == 200:
                return resp.json()
            resp.raise_for_status()

    async def delete_session(self, session_id: str, token: str) -> bool:
        url = f"{self.base_url}/monitoring_sessions?id=eq.{session_id}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.delete(url, headers=self._get_headers(token, prefer_return=False))
            return resp.status_code in (200, 204)

    async def get_user_preferences(self, user_id: str, token: str) -> Dict[str, Any]:
        """Fetches user preferences from Supabase, returning defaults if none exist yet."""
        defaults = {
            "user_id": user_id,
            "browser_notifications_enabled": False,
            "voice_alerts_enabled": False,
            "voice_volume": 0.8,
            "voice_rate": 1.0,
            "voice_pitch": 1.0,
            "quiet_mode_enabled": False,
            "selected_voice": None,
            "data_retention_days": None,
        }
        if not self.base_url:
            return defaults

        url = f"{self.base_url}/user_preferences?user_id=eq.{user_id}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=self._get_headers(token))
                if resp.status_code == 200:
                    rows = resp.json()
                    if rows:
                        defaults.update(rows[0])
        except Exception:
            pass
        return defaults

    async def upsert_user_preferences(self, user_id: str, token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Upserts user preferences in Supabase adhering to RLS."""
        clean_data = self.filter_preference_payload(payload)
        clean_data["user_id"] = user_id

        if not self.base_url:
            return clean_data

        url = f"{self.base_url}/user_preferences"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                url,
                headers=self._get_headers(token, prefer_return=True, upsert=True),
                json=clean_data
            )
            if resp.status_code in (200, 201):
                results = resp.json()
                return results[0] if results else clean_data
            resp.raise_for_status()

    async def delete_user_data(self, user_id: str, token: str) -> Dict[str, Any]:
        """
        Deletes all VisionGuard user data (sessions, events, preferences, profile).
        Auth account remains in Supabase Auth.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Delete sessions (cascades risk_events)
            sessions_url = f"{self.base_url}/monitoring_sessions?user_id=eq.{user_id}"
            await client.delete(sessions_url, headers=self._get_headers(token, prefer_return=False))
            
            # Delete personal goals
            goals_url = f"{self.base_url}/personal_goals?user_id=eq.{user_id}"
            await client.delete(goals_url, headers=self._get_headers(token, prefer_return=False))

            # Delete preferences
            pref_url = f"{self.base_url}/user_preferences?user_id=eq.{user_id}"
            await client.delete(pref_url, headers=self._get_headers(token, prefer_return=False))
            
            # Delete profile
            prof_url = f"{self.base_url}/profiles?id=eq.{user_id}"
            await client.delete(prof_url, headers=self._get_headers(token, prefer_return=False))
            
            return {
                "status": "success",
                "message": "All VisionGuard application data deleted successfully. Authentication account remains active.",
                "deleted_user_id": user_id
            }

    async def mark_stale_sessions_interrupted(self, user_id: str, token: str, current_session_id: Optional[str] = None) -> int:
        """
        Finds any ACTIVE sessions for this user (except current_session_id) and marks them INTERRUPTED.
        """
        url = f"{self.base_url}/monitoring_sessions?user_id=eq.{user_id}&status=eq.ACTIVE"
        if current_session_id:
            url += f"&id=neq.{current_session_id}"
            
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=self._get_headers(token))
            if resp.status_code != 200:
                return 0
            stale_sessions = resp.json()
            if not stale_sessions:
                return 0
                
            patch_url = url
            await client.patch(
                patch_url,
                headers=self._get_headers(token, prefer_return=False),
                json={"status": "INTERRUPTED"}
            )
            return len(stale_sessions)

    async def list_goals(self, user_id: str, token: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/personal_goals?user_id=eq.{user_id}&order=created_at.asc"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=self._get_headers(token))
            if resp.status_code == 200:
                return resp.json()
            resp.raise_for_status()

    async def upsert_goal(self, user_id: str, token: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        clean_data = self.filter_goal_payload(payload)
        clean_data["user_id"] = user_id
        url = f"{self.base_url}/personal_goals?on_conflict=user_id,goal_type"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                url,
                headers=self._get_headers(token, prefer_return=True, upsert=True),
                json=clean_data
            )
            if resp.status_code in (200, 201):
                rows = resp.json()
                return rows[0] if rows else clean_data
            resp.raise_for_status()

    async def delete_goal(self, goal_id: str, token: str) -> bool:
        url = f"{self.base_url}/personal_goals?id=eq.{goal_id}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.delete(url, headers=self._get_headers(token, prefer_return=False))
            return resp.status_code in (200, 204)

    async def list_sessions_in_range(
        self,
        token: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        query_params = [f"limit={limit}", "order=started_at.asc"]
        if start_time:
            query_params.append(f"started_at=gte.{start_time}")
        if end_time:
            query_params.append(f"started_at=lte.{end_time}")
        url = f"{self.base_url}/monitoring_sessions?{'&'.join(query_params)}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=self._get_headers(token))
            if resp.status_code == 200:
                return resp.json()
            resp.raise_for_status()
    async def cleanup_expired_sessions(self, user_id: str, token: str, retention_days: int) -> int:
        """
        Deletes completed historical sessions older than retention_days.

        Safety constraints:
        - Only targets status = 'COMPLETED'
        - Never deletes ACTIVE, INTERRUPTED, or in-progress sessions
        - Enforced under user's own RLS bearer token
        - Returns count of deleted sessions
        """
        if not self.base_url or retention_days <= 0:
            return 0

        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()

        url = (
            f"{self.base_url}/monitoring_sessions"
            f"?user_id=eq.{user_id}"
            f"&status=eq.COMPLETED"
            f"&started_at=lt.{cutoff}"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # First: count how many will be deleted
                count_resp = await client.get(
                    url + "&select=id",
                    headers=self._get_headers(token, prefer_return=False),
                )
                if count_resp.status_code != 200:
                    return 0
                rows = count_resp.json()
                if not rows:
                    return 0
                count = len(rows)
                # Delete
                await client.delete(url, headers=self._get_headers(token, prefer_return=False))
                return count
        except Exception:
            return 0


    async def list_events_in_range(
        self,
        token: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        session_ids: Optional[List[str]] = None,
        limit: int = 5000
    ) -> List[Dict[str, Any]]:
        query_params = [f"limit={limit}", "order=timestamp.asc"]
        if start_time:
            query_params.append(f"timestamp=gte.{start_time}")
        if end_time:
            query_params.append(f"timestamp=lte.{end_time}")
        if session_ids is not None:
            if not session_ids:
                return []
            ids_str = ",".join(session_ids)
            query_params.append(f"session_id=in.({ids_str})")
        url = f"{self.base_url}/risk_events?{'&'.join(query_params)}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=self._get_headers(token))
            if resp.status_code == 200:
                return resp.json()
            resp.raise_for_status()
