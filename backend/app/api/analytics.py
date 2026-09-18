from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.models import AuthenticatedUser
from app.auth.dependencies import get_current_user
from app.sessions.service import session_service
from app.sessions.models import AnalyticsSummary
from app.intelligence.models import (
    AnalyticsOverview, DailyTrendItem, TimeOfDayBucket, Insight
)
from app.intelligence.analytics_engine import (
    resolve_user_timezone, compute_analytics_overview,
    compute_daily_trends, compute_time_of_day_patterns
)
from app.intelligence.insight_engine import DeterministicInsightEngine

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Legacy Mission 06 summary preserved for backward compatibility.
    Computes aggregate analytics for the authenticated user from their sessions.
    """
    try:
        sessions = await session_service.repository.list_sessions(
            token=user.token, limit=200
        )
        if not sessions:
            return AnalyticsSummary()

        total_sessions = len(sessions)
        total_seconds = sum(float(s.get("duration_seconds") or 0.0) for s in sessions)
        total_good_posture = sum(float(s.get("good_posture_seconds") or 0.0) for s in sessions)
        total_risk_events = sum(int(s.get("risk_event_count") or 0) for s in sessions)
        total_interventions = sum(int(s.get("intervention_count") or 0) for s in sessions)

        good_posture_pct = (
            round((total_good_posture / total_seconds) * 100.0, 1)
            if total_seconds > 0 else 0.0
        )

        posture_weighted_sum = 0.0
        posture_time_sum = 0.0
        alertness_weighted_sum = 0.0
        alertness_time_sum = 0.0

        for s in sessions:
            dur = float(s.get("duration_seconds") or 0.0)
            p_score = s.get("average_posture_score")
            a_score = s.get("average_alertness_score")
            if p_score is not None and dur > 0:
                posture_weighted_sum += float(p_score) * dur
                posture_time_sum += dur
            if a_score is not None and dur > 0:
                alertness_weighted_sum += float(a_score) * dur
                alertness_time_sum += dur

        avg_posture = round(posture_weighted_sum / posture_time_sum, 1) if posture_time_sum > 0 else None
        avg_alertness = round(alertness_weighted_sum / alertness_time_sum, 1) if alertness_time_sum > 0 else None

        return AnalyticsSummary(
            total_sessions=total_sessions,
            total_monitored_seconds=round(total_seconds, 1),
            total_good_posture_seconds=round(total_good_posture, 1),
            good_posture_percentage=good_posture_pct,
            average_posture_score=avg_posture,
            average_alertness_score=avg_alertness,
            total_risk_events=total_risk_events,
            total_interventions=total_interventions,
            moderate_risk_count=0,
            high_risk_count=0
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate analytics summary: {str(e)}"
        )


async def _fetch_user_context(user: AuthenticatedUser, days: int, browser_tz: Optional[str]):
    prefs = await session_service.repository.get_user_preferences(user.id, user.token)
    saved_tz = prefs.get("timezone") if prefs else None
    resolved_tz = resolve_user_timezone(saved_tz, browser_tz)

    now_utc = datetime.now(timezone.utc)
    start_utc = now_utc - timedelta(days=days)
    start_iso = start_utc.isoformat()

    sessions = await session_service.repository.list_sessions_in_range(
        token=user.token, start_time=start_iso, limit=1000
    )
    session_ids = [s["id"] for s in sessions if "id" in s]
    events = await session_service.repository.list_events_in_range(
        token=user.token, start_time=start_iso, session_ids=session_ids, limit=5000
    )
    return resolved_tz, sessions, events, now_utc


@router.get("/overview", response_model=AnalyticsOverview)
async def get_analytics_overview(
    days: int = Query(default=30, ge=1, le=365),
    tz: Optional[str] = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user)
):
    try:
        resolved_tz, sessions, events, _ = await _fetch_user_context(user, days, tz)
        return compute_analytics_overview(sessions, events)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to compute analytics overview: {str(e)}"
        )


@router.get("/trends", response_model=List[DailyTrendItem])
async def get_daily_trends(
    days: int = Query(default=14, ge=1, le=90),
    tz: Optional[str] = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user)
):
    try:
        resolved_tz, sessions, events, now_utc = await _fetch_user_context(user, days, tz)
        now_local = now_utc.astimezone(resolved_tz)
        end_date = now_local.date()
        start_date = end_date - timedelta(days=days - 1)
        return compute_daily_trends(sessions, events, resolved_tz, start_date, end_date)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to compute daily trends: {str(e)}"
        )


@router.get("/patterns", response_model=List[TimeOfDayBucket])
async def get_time_of_day_patterns(
    days: int = Query(default=30, ge=1, le=365),
    tz: Optional[str] = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user)
):
    try:
        resolved_tz, sessions, events, _ = await _fetch_user_context(user, days, tz)
        return compute_time_of_day_patterns(sessions, events, resolved_tz)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to compute time of day patterns: {str(e)}"
        )


@router.get("/insights", response_model=List[Insight])
async def get_insights(
    days: int = Query(default=30, ge=1, le=365),
    tz: Optional[str] = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user)
):
    try:
        resolved_tz, sessions, events, now_utc = await _fetch_user_context(user, days, tz)
        now_local = now_utc.astimezone(resolved_tz)
        end_date = now_local.date()
        start_date = end_date - timedelta(days=days - 1)

        overview = compute_analytics_overview(sessions, events)
        trends = compute_daily_trends(sessions, events, resolved_tz, start_date, end_date)
        tod = compute_time_of_day_patterns(sessions, events, resolved_tz)

        return DeterministicInsightEngine.generate_insights(overview, trends, tod)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate insights: {str(e)}"
        )
