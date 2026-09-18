import math
from zoneinfo import ZoneInfo
from datetime import datetime, date, time, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from fastapi import HTTPException

from app.intelligence.models import (
    CoverageLevel, ModalityCoverage, CohortCoverage,
    AnalyticsOverview, DailyTrendItem, TimeOfDayBucket
)

POSTURE_CATEGORIES = {"POSTURE_SLOUCH", "POSTURE_LEAN", "POSTURE_HEAD_FORWARD", "POSTURE", "SLOUCH", "LEAN"}
ALERTNESS_CATEGORIES = {"DROWSINESS", "PROLONGED_FATIGUE", "ALERTNESS", "EYE_CLOSURE", "YAWN"}

def resolve_user_timezone(saved_tz: Optional[str], browser_tz: Optional[str] = None) -> ZoneInfo:
    """
    Resolves timezone in order:
    1. saved valid preference if non-null and non-empty
    2. browser IANA timezone if supplied and valid
    3. UTC fallback
    Validates with ZoneInfo. Raises HTTPException(400) if browser_tz is invalid when unsaved.
    """
    if saved_tz and saved_tz.strip():
        try:
            return ZoneInfo(saved_tz.strip())
        except Exception:
            # If saved corrupted, fall through to browser or UTC
            pass

    if browser_tz and browser_tz.strip():
        tz_clean = browser_tz.strip()
        try:
            return ZoneInfo(tz_clean)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid IANA timezone '{tz_clean}'")

    return ZoneInfo("UTC")


def compute_cohort_coverage(sessions: List[Dict[str, Any]]) -> CohortCoverage:
    total = len(sessions)
    if total == 0:
        return CohortCoverage(
            sessions_total=0,
            posture=ModalityCoverage(data_quality=CoverageLevel.UNAVAILABLE, sessions_with_known_exposure=0),
            alertness=ModalityCoverage(data_quality=CoverageLevel.UNAVAILABLE, sessions_with_known_exposure=0)
        )

    # 0.0 is KNOWN exposure, None is UNKNOWN
    posture_known = sum(1 for s in sessions if s.get("valid_posture_seconds") is not None)
    alertness_known = sum(1 for s in sessions if s.get("valid_alertness_seconds") is not None)

    if posture_known == total:
        p_quality = CoverageLevel.COMPLETE
    elif posture_known > 0:
        p_quality = CoverageLevel.PARTIAL
    else:
        p_quality = CoverageLevel.UNAVAILABLE

    if alertness_known == total:
        a_quality = CoverageLevel.COMPLETE
    elif alertness_known > 0:
        a_quality = CoverageLevel.PARTIAL
    else:
        a_quality = CoverageLevel.UNAVAILABLE

    return CohortCoverage(
        sessions_total=total,
        posture=ModalityCoverage(data_quality=p_quality, sessions_with_known_exposure=posture_known),
        alertness=ModalityCoverage(data_quality=a_quality, sessions_with_known_exposure=alertness_known)
    )


def compute_matching_cohort_rates(
    sessions: List[Dict[str, Any]],
    events: List[Dict[str, Any]]
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """
    Computes posture and alertness event rates per valid observation hour using STRICT cohort matching.
    Never divides all-session events by partial-session valid exposure.
    Also computes good_posture_percentage based only on sessions with valid_posture_seconds > 0.
    Returns: (good_posture_pct, posture_rate, alertness_rate, total_valid_posture_sec)
    """
    # 1. Posture cohort
    eligible_posture_sessions = {
        s["id"]: s for s in sessions
        if s.get("id") and s.get("valid_posture_seconds") is not None
    }
    
    total_valid_posture = sum(
        float(s["valid_posture_seconds"]) for s in eligible_posture_sessions.values()
    )
    total_good_posture = sum(
        float(s.get("good_posture_seconds") or 0.0) for s in eligible_posture_sessions.values()
    )

    good_posture_pct = None
    if total_valid_posture > 0:
        good_posture_pct = round(min(100.0, (total_good_posture / total_valid_posture) * 100.0), 1)

    posture_rate = None
    if total_valid_posture >= 300.0:  # Minimum 5 mins valid exposure
        eligible_posture_ids = set(eligible_posture_sessions.keys())
        # Numerator: STARTED events belonging ONLY to eligible sessions
        eligible_posture_events = [
            e for e in events
            if e.get("session_id") in eligible_posture_ids
            and str(e.get("category", "")).upper() in POSTURE_CATEGORIES
            and str(e.get("lifecycle", "STARTED")).upper() == "STARTED"
        ]
        posture_rate = round(len(eligible_posture_events) / (total_valid_posture / 3600.0), 2)

    # 2. Alertness cohort
    eligible_alertness_sessions = {
        s["id"]: s for s in sessions
        if s.get("id") and s.get("valid_alertness_seconds") is not None
    }
    total_valid_alertness = sum(
        float(s["valid_alertness_seconds"]) for s in eligible_alertness_sessions.values()
    )

    alertness_rate = None
    if total_valid_alertness >= 300.0:  # Minimum 5 mins valid exposure
        eligible_alertness_ids = set(eligible_alertness_sessions.keys())
        eligible_alertness_events = [
            e for e in events
            if e.get("session_id") in eligible_alertness_ids
            and str(e.get("category", "")).upper() in ALERTNESS_CATEGORIES
            and str(e.get("lifecycle", "STARTED")).upper() == "STARTED"
        ]
        alertness_rate = round(len(eligible_alertness_events) / (total_valid_alertness / 3600.0), 2)

    return good_posture_pct, posture_rate, alertness_rate, (total_valid_posture if eligible_posture_sessions else None)


def compute_analytics_overview(
    sessions: List[Dict[str, Any]],
    events: List[Dict[str, Any]]
) -> AnalyticsOverview:
    coverage = compute_cohort_coverage(sessions)
    total_monitored = round(sum(float(s.get("duration_seconds") or 0.0) for s in sessions), 1)
    total_good = round(sum(float(s.get("good_posture_seconds") or 0.0) for s in sessions), 1)
    total_posture_risk = round(sum(float(s.get("posture_risk_seconds") or 0.0) for s in sessions), 1)
    total_alertness_risk = round(sum(float(s.get("alertness_risk_seconds") or 0.0) for s in sessions), 1)
    total_interventions = sum(int(s.get("intervention_count") or 0) for s in sessions)
    total_events = len(events)

    # Time-weighted average scores across sessions with valid scores
    p_scores = [
        (float(s["average_posture_score"]), float(s.get("valid_posture_seconds") or s.get("duration_seconds") or 1.0))
        for s in sessions if s.get("average_posture_score") is not None
    ]
    avg_posture = None
    if p_scores:
        sum_weight = sum(w for _, w in p_scores)
        if sum_weight > 0:
            avg_posture = round(sum(sc * w for sc, w in p_scores) / sum_weight, 1)

    a_scores = [
        (float(s["average_alertness_score"]), float(s.get("valid_alertness_seconds") or s.get("duration_seconds") or 1.0))
        for s in sessions if s.get("average_alertness_score") is not None
    ]
    avg_alertness = None
    if a_scores:
        sum_weight = sum(w for _, w in a_scores)
        if sum_weight > 0:
            avg_alertness = round(sum(sc * w for sc, w in a_scores) / sum_weight, 1)

    good_pct, posture_rate, alertness_rate, _ = compute_matching_cohort_rates(sessions, events)

    return AnalyticsOverview(
        total_monitored_seconds=total_monitored,
        total_sessions=len(sessions),
        good_posture_seconds=total_good,
        good_posture_percentage=good_pct,
        posture_risk_seconds=total_posture_risk,
        alertness_risk_seconds=total_alertness_risk,
        posture_events_per_valid_observation_hour=posture_rate,
        alertness_events_per_valid_observation_hour=alertness_rate,
        average_posture_score=avg_posture,
        average_alertness_score=avg_alertness,
        total_risk_events=total_events,
        total_interventions=total_interventions,
        coverage=coverage
    )


def compute_daily_trends(
    sessions: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    tz: ZoneInfo,
    start_date: date,
    end_date: date
) -> List[DailyTrendItem]:
    """
    Groups sessions and events by calendar date in the resolved timezone.
    Returns complete continuous date range (filling empty days with 0s).
    """
    # Group sessions by local date
    sessions_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for s in sessions:
        st_raw = s.get("started_at")
        if not st_raw:
            continue
        try:
            if isinstance(st_raw, str):
                dt_utc = datetime.fromisoformat(st_raw)
            else:
                dt_utc = st_raw
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            local_dt = dt_utc.astimezone(tz)
            d_str = local_dt.date().isoformat()
            sessions_by_date.setdefault(d_str, []).append(s)
        except Exception:
            continue

    # Group events by local date
    events_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for e in events:
        ts_raw = e.get("timestamp")
        if not ts_raw:
            continue
        try:
            if isinstance(ts_raw, str):
                dt_utc = datetime.fromisoformat(ts_raw)
            else:
                dt_utc = ts_raw
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            local_dt = dt_utc.astimezone(tz)
            d_str = local_dt.date().isoformat()
            events_by_date.setdefault(d_str, []).append(e)
        except Exception:
            continue

    results: List[DailyTrendItem] = []
    curr = start_date
    while curr <= end_date:
        d_str = curr.isoformat()
        day_sessions = sessions_by_date.get(d_str, [])
        day_events = events_by_date.get(d_str, [])

        coverage = compute_cohort_coverage(day_sessions)
        day_monitored = round(sum(float(s.get("duration_seconds") or 0.0) for s in day_sessions), 1)
        day_good = round(sum(float(s.get("good_posture_seconds") or 0.0) for s in day_sessions), 1)
        day_interventions = sum(int(s.get("intervention_count") or 0) for s in day_sessions)

        good_pct, p_rate, a_rate, valid_posture_sec = compute_matching_cohort_rates(day_sessions, day_events)

        # Average posture/alertness score for day
        p_scores = [float(s["average_posture_score"]) for s in day_sessions if s.get("average_posture_score") is not None]
        avg_posture = round(sum(p_scores) / len(p_scores), 1) if p_scores else None

        a_scores = [float(s["average_alertness_score"]) for s in day_sessions if s.get("average_alertness_score") is not None]
        avg_alertness = round(sum(a_scores) / len(a_scores), 1) if a_scores else None

        results.append(DailyTrendItem(
            date=d_str,
            total_monitored_seconds=day_monitored,
            good_posture_seconds=day_good,
            valid_posture_seconds=valid_posture_sec,
            good_posture_percentage=good_pct,
            posture_events_per_valid_observation_hour=p_rate,
            alertness_events_per_valid_observation_hour=a_rate,
            average_posture_score=avg_posture,
            average_alertness_score=avg_alertness,
            risk_event_count=len(day_events),
            intervention_count=day_interventions,
            coverage=coverage
        ))
        curr += timedelta(days=1)

    return results


def split_session_into_time_buckets(
    start_dt: datetime,
    duration_sec: float
) -> Dict[str, float]:
    """
    Slices a continuous session duration across local clock time boundaries:
    - MORNING:   06:00 to 12:00
    - AFTERNOON: 12:00 to 17:00
    - EVENING:   17:00 to 22:00
    - NIGHT:     22:00 to 06:00
    Returns monitored exposure seconds per bucket.
    """
    bucket_allocations = {"MORNING": 0.0, "AFTERNOON": 0.0, "EVENING": 0.0, "NIGHT": 0.0}
    if duration_sec <= 0:
        return bucket_allocations

    curr_time = start_dt
    end_time = start_dt + timedelta(seconds=duration_sec)

    while curr_time < end_time:
        # Determine current bucket and when it ends
        hour = curr_time.hour
        if 6 <= hour < 12:
            bucket = "MORNING"
            boundary = curr_time.replace(hour=12, minute=0, second=0, microsecond=0)
        elif 12 <= hour < 17:
            bucket = "AFTERNOON"
            boundary = curr_time.replace(hour=17, minute=0, second=0, microsecond=0)
        elif 17 <= hour < 22:
            bucket = "EVENING"
            boundary = curr_time.replace(hour=22, minute=0, second=0, microsecond=0)
        else:
            bucket = "NIGHT"
            if hour >= 22:
                # Boundary is next day 06:00
                next_day = curr_time.date() + timedelta(days=1)
                boundary = datetime.combine(next_day, time(6, 0), tzinfo=curr_time.tzinfo)
            else:
                boundary = curr_time.replace(hour=6, minute=0, second=0, microsecond=0)

        chunk_end = min(end_time, boundary)
        chunk_seconds = (chunk_end - curr_time).total_seconds()
        bucket_allocations[bucket] += max(0.0, chunk_seconds)
        curr_time = chunk_end

    return bucket_allocations


def compute_time_of_day_patterns(
    sessions: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    tz: ZoneInfo
) -> List[TimeOfDayBucket]:
    """
    Allocates continuous monitoring exposure to time buckets and maps risk events.
    Calculates rate per monitored hour for each bucket.
    """
    buckets = {
        "MORNING": {"label": "Morning (06:00 - 12:00)", "exposure": 0.0, "events": 0},
        "AFTERNOON": {"label": "Afternoon (12:00 - 17:00)", "exposure": 0.0, "events": 0},
        "EVENING": {"label": "Evening (17:00 - 22:00)", "exposure": 0.0, "events": 0},
        "NIGHT": {"label": "Night (22:00 - 06:00)", "exposure": 0.0, "events": 0},
    }

    for s in sessions:
        st_raw = s.get("started_at")
        dur = float(s.get("duration_seconds") or 0.0)
        if not st_raw or dur <= 0:
            continue
        try:
            if isinstance(st_raw, str):
                dt_utc = datetime.fromisoformat(st_raw)
            else:
                dt_utc = st_raw
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            local_start = dt_utc.astimezone(tz)
            sliced = split_session_into_time_buckets(local_start, dur)
            for b_name, b_sec in sliced.items():
                buckets[b_name]["exposure"] += b_sec
        except Exception:
            continue

    # Allocate events
    for e in events:
        ts_raw = e.get("timestamp")
        if not ts_raw:
            continue
        try:
            if isinstance(ts_raw, str):
                dt_utc = datetime.fromisoformat(ts_raw)
            else:
                dt_utc = ts_raw
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            local_dt = dt_utc.astimezone(tz)
            hour = local_dt.hour
            if 6 <= hour < 12:
                b_name = "MORNING"
            elif 12 <= hour < 17:
                b_name = "AFTERNOON"
            elif 17 <= hour < 22:
                b_name = "EVENING"
            else:
                b_name = "NIGHT"
            buckets[b_name]["events"] += 1
        except Exception:
            continue

    results: List[TimeOfDayBucket] = []
    order = ["MORNING", "AFTERNOON", "EVENING", "NIGHT"]
    for b_name in order:
        b_data = buckets[b_name]
        exp_sec = round(b_data["exposure"], 1)
        ev_count = b_data["events"]
        rate = None
        if exp_sec >= 300.0:  # At least 5 mins exposure
            rate = round(ev_count / (exp_sec / 3600.0), 2)

        results.append(TimeOfDayBucket(
            bucket=b_name,
            label=b_data["label"],
            monitored_exposure_seconds=exp_sec,
            risk_event_count=ev_count,
            events_per_monitored_hour=rate
        ))

    return results
