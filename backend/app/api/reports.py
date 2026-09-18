import csv
import io
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.auth.models import AuthenticatedUser
from app.auth.dependencies import get_current_user
from app.sessions.service import session_service
from app.intelligence.models import (
    AnalyticsOverview, DailyTrendItem, TimeOfDayBucket, Insight, GoalType
)
from app.intelligence.analytics_engine import (
    resolve_user_timezone, compute_analytics_overview,
    compute_daily_trends, compute_time_of_day_patterns, compute_cohort_coverage
)
from app.intelligence.insight_engine import DeterministicInsightEngine

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/session/{session_id}")
async def get_session_report(
    session_id: str,
    tz: Optional[str] = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user)
) -> Dict[str, Any]:
    try:
        session = await session_service.repository.get_session(session_id, user.token)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        events = await session_service.repository.get_session_events(session_id, user.token)
        coverage = compute_cohort_coverage([session])
        overview = compute_analytics_overview([session], events)

        # Categorize events
        event_breakdown: Dict[str, int] = {}
        severity_breakdown: Dict[str, int] = {}
        for e in events:
            cat = e.get("category", "OTHER")
            sev = e.get("severity", "LOW")
            event_breakdown[cat] = event_breakdown.get(cat, 0) + 1
            severity_breakdown[sev] = severity_breakdown.get(sev, 0) + 1

        return {
            "session": session,
            "coverage": coverage,
            "overview": overview,
            "event_breakdown": event_breakdown,
            "severity_breakdown": severity_breakdown,
            "events": events
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate session report: {str(e)}"
        )


@router.get("/weekly")
async def get_weekly_report(
    week_offset: int = Query(default=0, ge=-52, le=0),
    tz: Optional[str] = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user)
) -> Dict[str, Any]:
    try:
        prefs = await session_service.repository.get_user_preferences(user.id, user.token)
        saved_tz = prefs.get("timezone") if prefs else None
        resolved_tz = resolve_user_timezone(saved_tz, tz)

        now_local = datetime.now(resolved_tz)
        # Find Monday of current week
        days_since_monday = now_local.weekday()
        current_monday = now_local.date() - timedelta(days=days_since_monday)
        target_monday = current_monday + timedelta(weeks=week_offset)
        target_sunday = target_monday + timedelta(days=6)

        # Range in UTC
        start_local = datetime.combine(target_monday, datetime.min.time(), tzinfo=resolved_tz)
        end_local = datetime.combine(target_sunday, datetime.max.time(), tzinfo=resolved_tz)

        start_utc_iso = start_local.astimezone(timezone.utc).isoformat()
        end_utc_iso = end_local.astimezone(timezone.utc).isoformat()

        sessions = await session_service.repository.list_sessions_in_range(
            token=user.token, start_time=start_utc_iso, end_time=end_utc_iso, limit=1000
        )
        session_ids = [s["id"] for s in sessions if "id" in s]
        events = await session_service.repository.list_events_in_range(
            token=user.token, start_time=start_utc_iso, end_time=end_utc_iso, session_ids=session_ids, limit=5000
        )

        overview = compute_analytics_overview(sessions, events)
        daily_trends = compute_daily_trends(sessions, events, resolved_tz, target_monday, target_sunday)
        tod_patterns = compute_time_of_day_patterns(sessions, events, resolved_tz)
        insights = DeterministicInsightEngine.generate_insights(overview, daily_trends, tod_patterns)

        return {
            "week_start": target_monday.isoformat(),
            "week_end": target_sunday.isoformat(),
            "timezone": str(resolved_tz),
            "overview": overview,
            "daily_trends": daily_trends,
            "time_of_day_patterns": tod_patterns,
            "insights": insights
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate weekly report: {str(e)}"
        )


@router.get("/export/sessions/csv")
async def export_sessions_csv(
    days: int = Query(default=30, ge=1, le=365),
    user: AuthenticatedUser = Depends(get_current_user)
):
    try:
        now_utc = datetime.now(timezone.utc)
        start_utc = now_utc - timedelta(days=days)
        sessions = await session_service.repository.list_sessions_in_range(
            token=user.token, start_time=start_utc.isoformat(), limit=5000
        )

        output = io.StringIO()
        fieldnames = [
            "session_id", "started_at", "ended_at", "duration_seconds",
            "good_posture_seconds", "posture_risk_seconds", "alertness_risk_seconds",
            "valid_posture_seconds", "valid_alertness_seconds", "average_posture_score",
            "average_alertness_score", "risk_event_count", "intervention_count",
            "status", "device_name"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for s in sessions:
            writer.writerow({
                "session_id": s.get("id"),
                "started_at": s.get("started_at"),
                "ended_at": s.get("ended_at"),
                "duration_seconds": s.get("duration_seconds"),
                "good_posture_seconds": s.get("good_posture_seconds"),
                "posture_risk_seconds": s.get("posture_risk_seconds"),
                "alertness_risk_seconds": s.get("alertness_risk_seconds"),
                "valid_posture_seconds": s.get("valid_posture_seconds"),
                "valid_alertness_seconds": s.get("valid_alertness_seconds"),
                "average_posture_score": s.get("average_posture_score"),
                "average_alertness_score": s.get("average_alertness_score"),
                "risk_event_count": s.get("risk_event_count"),
                "intervention_count": s.get("intervention_count"),
                "status": s.get("status"),
                "device_name": s.get("device_name")
            })

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=visionguard_sessions_{days}d.csv"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to export sessions CSV: {str(e)}"
        )


@router.get("/export/risk-events/csv")
async def export_risk_events_csv(
    days: int = Query(default=30, ge=1, le=365),
    user: AuthenticatedUser = Depends(get_current_user)
):
    try:
        now_utc = datetime.now(timezone.utc)
        start_utc = now_utc - timedelta(days=days)
        events = await session_service.repository.list_events_in_range(
            token=user.token, start_time=start_utc.isoformat(), limit=10000
        )

        output = io.StringIO()
        fieldnames = [
            "event_id", "session_id", "timestamp", "category",
            "severity", "reason", "lifecycle", "duration_seconds"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for e in events:
            writer.writerow({
                "event_id": e.get("id"),
                "session_id": e.get("session_id"),
                "timestamp": e.get("timestamp"),
                "category": e.get("category"),
                "severity": e.get("severity"),
                "reason": e.get("reason"),
                "lifecycle": e.get("lifecycle"),
                "duration_seconds": e.get("duration_seconds")
            })

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=visionguard_risk_events_{days}d.csv"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to export risk events CSV: {str(e)}"
        )
