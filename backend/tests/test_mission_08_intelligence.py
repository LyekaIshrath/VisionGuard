import io
import csv
import pytest
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.sessions.aggregator import SessionAggregator
from app.human_state.models import HumanState
from app.intelligence.models import CoverageLevel, GoalType
from app.intelligence.analytics_engine import (
    resolve_user_timezone, compute_cohort_coverage,
    compute_matching_cohort_rates, compute_analytics_overview,
    compute_daily_trends, split_session_into_time_buckets,
    compute_time_of_day_patterns
)
from app.intelligence.insight_engine import DeterministicInsightEngine
from app.auth.models import AuthenticatedUser
from app.auth.dependencies import get_current_user
from app.sessions.service import session_service

client = TestClient(app)

# Mock authenticated user
TEST_USER = AuthenticatedUser(
    id="test-user-mission-08",
    email="intelligence@visionguard.test",
    role="authenticated",
    token="mock-intel-token"
)

@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    yield
    app.dependency_overrides.pop(get_current_user, None)


# =========================================================================
# 1. TIMEZONE TESTS
# =========================================================================

def test_legacy_timezone_remains_null_after_migration():
    """Confirms NULL is treated as no saved preference, not auto-converted to UTC."""
    tz = resolve_user_timezone(saved_tz=None, browser_tz=None)
    assert tz == ZoneInfo("UTC")  # falls back to UTC when nothing provided


def test_null_saved_timezone_uses_valid_browser_timezone():
    """Unsaved preference dynamically uses browser IANA timezone."""
    tz = resolve_user_timezone(saved_tz=None, browser_tz="America/New_York")
    assert tz == ZoneInfo("America/New_York")

    tz_tokyo = resolve_user_timezone(saved_tz=None, browser_tz="Asia/Tokyo")
    assert tz_tokyo == ZoneInfo("Asia/Tokyo")


def test_null_saved_timezone_without_browser_falls_back_utc():
    """No saved preference and no browser timezone falls back safely to UTC."""
    tz = resolve_user_timezone(saved_tz=None, browser_tz=None)
    assert tz == ZoneInfo("UTC")

    tz_empty = resolve_user_timezone(saved_tz="", browser_tz="")
    assert tz_empty == ZoneInfo("UTC")


def test_saved_timezone_has_priority():
    """Saved valid preference overrides any browser-sent query parameter."""
    tz = resolve_user_timezone(saved_tz="Europe/London", browser_tz="America/New_York")
    assert tz == ZoneInfo("Europe/London")


def test_invalid_browser_timezone_returns_400():
    """Invalid browser IANA timezone raises HTTP 400."""
    with pytest.raises(HTTPException) as exc:
        resolve_user_timezone(saved_tz=None, browser_tz="Mars/Olympus_Mons")
    assert exc.value.status_code == 400
    assert "Invalid IANA timezone" in exc.value.detail


def test_invalid_timezone_cannot_be_persisted():
    """API rejects saving an invalid timezone string with 400 Bad Request."""
    response = client.put(
        "/api/v1/user/preferences",
        json={"timezone": "Invalid/Fake_Zone"}
    )
    assert response.status_code == 400
    assert "Invalid IANA timezone" in response.json()["detail"]


# =========================================================================
# 2. PARTIAL RATE & COHORT TESTS
# =========================================================================

def test_partial_posture_rate_uses_matching_session_cohort():
    """
    Never divide events from all sessions by valid exposure from only some sessions.
    Numerator must strictly count events belonging to the eligible session cohort.
    """
    # 2 sessions: S1 has valid posture exposure (1800s / 0.5h), S2 is legacy (valid_posture_seconds=None)
    sessions = [
        {"id": "s1", "valid_posture_seconds": 1800.0, "duration_seconds": 1800.0, "good_posture_seconds": 1500.0},
        {"id": "s2", "valid_posture_seconds": None, "duration_seconds": 3600.0, "good_posture_seconds": 3000.0},
    ]
    # Events: 2 belong to s1, 5 belong to s2
    events = [
        {"session_id": "s1", "category": "POSTURE_SLOUCH", "lifecycle": "STARTED"},
        {"session_id": "s1", "category": "POSTURE_LEAN", "lifecycle": "STARTED"},
        {"session_id": "s2", "category": "POSTURE_SLOUCH", "lifecycle": "STARTED"},
        {"session_id": "s2", "category": "POSTURE_SLOUCH", "lifecycle": "STARTED"},
        {"session_id": "s2", "category": "POSTURE_SLOUCH", "lifecycle": "STARTED"},
        {"session_id": "s2", "category": "POSTURE_SLOUCH", "lifecycle": "STARTED"},
        {"session_id": "s2", "category": "POSTURE_SLOUCH", "lifecycle": "STARTED"},
    ]

    good_pct, p_rate, a_rate, valid_p_sec = compute_matching_cohort_rates(sessions, events)

    # Eligible exposure: 1800s = 0.5h
    # Eligible events: ONLY the 2 events from s1!
    # Expected rate: 2 / 0.5 = 4.0 events/hr
    # Under NO circumstance should it be (2 + 5) / 0.5 = 14.0!
    assert p_rate == 4.0
    # Good posture percentage: 1500 / 1800 = 83.3%
    assert good_pct == 83.3


def test_partial_alertness_rate_uses_matching_session_cohort():
    """Equivalent strict cohort matching for alertness rate."""
    sessions = [
        {"id": "s1", "valid_alertness_seconds": 3600.0, "duration_seconds": 3600.0},
        {"id": "s2", "valid_alertness_seconds": None, "duration_seconds": 1800.0},
    ]
    events = [
        {"session_id": "s1", "category": "DROWSINESS", "lifecycle": "STARTED"},
        {"session_id": "s2", "category": "DROWSINESS", "lifecycle": "STARTED"},
        {"session_id": "s2", "category": "DROWSINESS", "lifecycle": "STARTED"},
    ]

    _, _, a_rate, _ = compute_matching_cohort_rates(sessions, events)
    # Only 1 event from s1 divided by 1.0 hour = 1.0
    assert a_rate == 1.0


def test_legacy_events_not_divided_by_new_valid_exposure():
    """Legacy sessions with unknown exposure cannot inflate valid-exposure rates."""
    sessions = [
        {"id": "legacy_1", "valid_posture_seconds": None, "duration_seconds": 7200.0},
        {"id": "new_1", "valid_posture_seconds": 3600.0, "duration_seconds": 3600.0, "good_posture_seconds": 3200.0}
    ]
    events = [
        {"session_id": "legacy_1", "category": "POSTURE_SLOUCH", "lifecycle": "STARTED"},
        {"session_id": "legacy_1", "category": "POSTURE_SLOUCH", "lifecycle": "STARTED"},
        {"session_id": "legacy_1", "category": "POSTURE_SLOUCH", "lifecycle": "STARTED"},
        {"session_id": "new_1", "category": "POSTURE_SLOUCH", "lifecycle": "STARTED"}
    ]
    good_pct, p_rate, _, _ = compute_matching_cohort_rates(sessions, events)
    assert p_rate == 1.0  # 1 event from new_1 / 1.0 hour


def test_known_zero_exposure_counts_as_known_for_coverage():
    """0.0 is KNOWN exposure and counts toward coverage completeness. NULL means UNKNOWN."""
    sessions = [
        {"id": "s1", "valid_posture_seconds": 0.0, "valid_alertness_seconds": 0.0},
        {"id": "s2", "valid_posture_seconds": 1200.0, "valid_alertness_seconds": 1200.0}
    ]
    coverage = compute_cohort_coverage(sessions)
    # Both have known exposure (0.0 and 1200.0), so data quality is COMPLETE
    assert coverage.posture.data_quality == CoverageLevel.COMPLETE
    assert coverage.posture.sessions_with_known_exposure == 2
    assert coverage.alertness.data_quality == CoverageLevel.COMPLETE
    assert coverage.alertness.sessions_with_known_exposure == 2


def test_posture_and_alertness_quality_can_differ():
    """Posture and alertness modalities must have independent coverage tracking."""
    sessions = [
        {"id": "s1", "valid_posture_seconds": 1000.0, "valid_alertness_seconds": None},
        {"id": "s2", "valid_posture_seconds": 1500.0, "valid_alertness_seconds": None}
    ]
    coverage = compute_cohort_coverage(sessions)
    assert coverage.posture.data_quality == CoverageLevel.COMPLETE
    assert coverage.posture.sessions_with_known_exposure == 2
    assert coverage.alertness.data_quality == CoverageLevel.UNAVAILABLE
    assert coverage.alertness.sessions_with_known_exposure == 0


# =========================================================================
# 3. AGGREGATOR & EXPOSURE PERSISTENCE TESTS
# =========================================================================

def test_aggregator_persists_valid_exposure_seconds():
    """SessionAggregator calculates and returns valid_posture_seconds and valid_alertness_seconds."""
    agg = SessionAggregator("test-s", "test-u")
    
    # Add good calibrated posture sample
    state_valid = HumanState(
        track_id="user_1",
        posture_status="GOOD",
        posture_score=95.0,
        alertness_status="ALERT",
        alertness_score=90.0
    )
    agg.add_sample(state_valid, current_mono=100.0)
    agg.add_sample(state_valid, current_mono=100.5)  # 0.5s valid
    
    # Add uncalibrated / unknown sample
    state_unknown = HumanState(
        track_id="user_1",
        posture_status="UNKNOWN",
        posture_score=None,
        alertness_status="NOT_CALIBRATED",
        alertness_score=None
    )
    agg.add_sample(state_unknown, current_mono=101.5)  # 1.0s uncalibrated

    summary = agg.get_summary()
    assert "valid_posture_seconds" in summary
    assert "valid_alertness_seconds" in summary
    assert summary["valid_posture_seconds"] == 0.5
    assert summary["valid_alertness_seconds"] == 0.5
    assert summary["duration_seconds"] == 1.5


def test_time_of_day_slicing_continuous_exposure():
    """Continuous session duration correctly splits across 06:00, 12:00, 17:00, 22:00 boundaries."""
    tz = ZoneInfo("UTC")
    # Session from 11:30 to 12:30 (1 hour = 3600s). 30 min in MORNING, 30 min in AFTERNOON.
    start = datetime(2026, 9, 18, 11, 30, 0, tzinfo=tz)
    sliced = split_session_into_time_buckets(start, 3600.0)
    assert round(sliced["MORNING"]) == 1800
    assert round(sliced["AFTERNOON"]) == 1800
    assert round(sliced["EVENING"]) == 0
    assert round(sliced["NIGHT"]) == 0


def test_deterministic_insights_thresholds():
    """InsightEngine enforces data thresholds and flags afternoon dips accurately."""
    # Under 1 hour total exposure -> INSUFFICIENT_DATA
    overview = compute_analytics_overview([
        {"id": "s1", "duration_seconds": 1500.0, "valid_posture_seconds": 1500.0}
    ], [])
    insights = DeterministicInsightEngine.generate_insights(overview, [], [])
    assert len(insights) == 1
    assert insights[0].type == "INSUFFICIENT_DATA"

    # Sufficient data with afternoon risk dip
    tod_buckets = [
        {"bucket": "MORNING", "label": "Morning", "monitored_exposure_seconds": 3600.0, "risk_event_count": 1, "events_per_monitored_hour": 1.0},
        {"bucket": "AFTERNOON", "label": "Afternoon", "monitored_exposure_seconds": 3600.0, "risk_event_count": 6, "events_per_monitored_hour": 6.0},
        {"bucket": "EVENING", "label": "Evening", "monitored_exposure_seconds": 0.0, "risk_event_count": 0, "events_per_monitored_hour": None},
        {"bucket": "NIGHT", "label": "Night", "monitored_exposure_seconds": 0.0, "risk_event_count": 0, "events_per_monitored_hour": None}
    ]
    overview_large = compute_analytics_overview([
        {"id": "s1", "duration_seconds": 7200.0, "valid_posture_seconds": 7200.0, "good_posture_seconds": 6000.0}
    ], [{"id": f"e{i}", "session_id": "s1", "category": "POSTURE", "lifecycle": "STARTED"} for i in range(7)])
    
    from app.intelligence.models import TimeOfDayBucket
    tod_objs = [TimeOfDayBucket(**b) for b in tod_buckets]
    insights_full = DeterministicInsightEngine.generate_insights(overview_large, [], tod_objs)
    dip_insights = [i for i in insights_full if i.id == "afternoon-risk-dip"]
    assert len(dip_insights) == 1
    assert "higher in the afternoon" in dip_insights[0].description


# =========================================================================
# 4. PERSONAL GOALS VALIDATION TESTS
# =========================================================================

def test_personal_goals_validation_and_crud():
    """Validates goal constraints (target > 0, posture <= 100)."""
    # Invalid negative target
    res_neg = client.put(
        "/api/v1/goals",
        json={"goal_type": "DAILY_MONITORING_MINUTES", "target_value": -10.0}
    )
    assert res_neg.status_code == 400

    # Invalid posture pct > 100%
    res_over = client.put(
        "/api/v1/goals",
        json={"goal_type": "GOOD_POSTURE_PERCENTAGE", "target_value": 150.0}
    )
    assert res_over.status_code == 400


# =========================================================================
# 5. CSV EXPORT PRIVACY WHITELIST TESTS
# =========================================================================

def test_reports_export_sessions_csv_whitelist(monkeypatch):
    """Sessions CSV export includes only approved columns, never raw telemetry."""
    async def mock_list_sessions(*args, **kwargs):
        return [{
            "id": "s-123", "started_at": "2026-09-18T10:00:00Z", "ended_at": "2026-09-18T11:00:00Z",
            "duration_seconds": 3600.0, "good_posture_seconds": 3000.0, "posture_risk_seconds": 300.0,
            "alertness_risk_seconds": 0.0, "valid_posture_seconds": 3600.0, "valid_alertness_seconds": 3600.0,
            "average_posture_score": 85.0, "average_alertness_score": 90.0, "risk_event_count": 2,
            "intervention_count": 1, "status": "COMPLETED", "device_name": "VisionGuard Desktop"
        }]
    monkeypatch.setattr(session_service.repository, "list_sessions_in_range", mock_list_sessions)

    response = client.get("/api/v1/reports/export/sessions/csv?days=7")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    
    reader = csv.reader(io.StringIO(response.text))
    header = next(reader)
    expected_header = [
        "session_id", "started_at", "ended_at", "duration_seconds",
        "good_posture_seconds", "posture_risk_seconds", "alertness_risk_seconds",
        "valid_posture_seconds", "valid_alertness_seconds", "average_posture_score",
        "average_alertness_score", "risk_event_count", "intervention_count",
        "status", "device_name"
    ]
    assert header == expected_header
    assert "landmark" not in header
    assert "frame" not in header


def test_reports_export_risk_events_csv_whitelist(monkeypatch):
    """Risk Events CSV export includes only approved columns, never biometric vectors."""
    async def mock_list_events(*args, **kwargs):
        return [{
            "id": "e-123", "session_id": "s-123", "timestamp": "2026-09-18T10:15:00Z",
            "category": "POSTURE_SLOUCH", "severity": "MODERATE", "reason": "Forward head posture",
            "lifecycle": "STARTED", "duration_seconds": 15.0
        }]
    monkeypatch.setattr(session_service.repository, "list_events_in_range", mock_list_events)

    response = client.get("/api/v1/reports/export/risk-events/csv?days=7")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    
    reader = csv.reader(io.StringIO(response.text))
    header = next(reader)
    expected_header = [
        "event_id", "session_id", "timestamp", "category",
        "severity", "reason", "lifecycle", "duration_seconds"
    ]
    assert header == expected_header
