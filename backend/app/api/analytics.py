from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from app.auth.models import AuthenticatedUser
from app.auth.dependencies import get_current_user
from app.sessions.service import session_service
from app.sessions.models import AnalyticsSummary

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Computes aggregate analytics for the authenticated user from their sessions.
    Guarantees user isolation through RLS token forwarding.
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

        # Time-weighted average across sessions
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
