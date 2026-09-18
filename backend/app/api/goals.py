import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.auth.models import AuthenticatedUser
from app.auth.dependencies import get_current_user
from app.sessions.service import session_service
from app.intelligence.models import (
    GoalType, PersonalGoalCreate, PersonalGoalRecord
)
from app.intelligence.analytics_engine import (
    resolve_user_timezone, compute_analytics_overview
)

router = APIRouter(prefix="/goals", tags=["goals"])

@router.get("", response_model=List[PersonalGoalRecord])
async def list_goals(
    tz: Optional[str] = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user)
):
    try:
        prefs = await session_service.repository.get_user_preferences(user.id, user.token)
        saved_tz = prefs.get("timezone") if prefs else None
        resolved_tz = resolve_user_timezone(saved_tz, tz)

        raw_goals = await session_service.repository.list_goals(user.id, user.token)

        # Get today's sessions and events to compute live progress
        now_local = datetime.now(resolved_tz)
        today_start_local = datetime.combine(now_local.date(), datetime.min.time(), tzinfo=resolved_tz)
        today_start_utc = today_start_local.astimezone(timezone.utc).isoformat()

        today_sessions = await session_service.repository.list_sessions_in_range(
            token=user.token, start_time=today_start_utc, limit=100
        )
        today_session_ids = [s["id"] for s in today_sessions if "id" in s]
        today_events = await session_service.repository.list_events_in_range(
            token=user.token, start_time=today_start_utc, session_ids=today_session_ids, limit=1000
        )
        overview = compute_analytics_overview(today_sessions, today_events)

        records: List[PersonalGoalRecord] = []
        for g in raw_goals:
            g_type = g.get("goal_type")
            target = float(g.get("target_value") or 0.0)
            current_val = None
            progress = None
            achieved = False

            if g_type == GoalType.DAILY_MONITORING_MINUTES.value:
                monitored_min = round(overview.total_monitored_seconds / 60.0, 1)
                current_val = monitored_min
                progress = round(min(100.0, (monitored_min / target) * 100.0), 1) if target > 0 else 0.0
                achieved = monitored_min >= target

            elif g_type == GoalType.GOOD_POSTURE_PERCENTAGE.value:
                current_val = overview.good_posture_percentage
                if current_val is not None:
                    progress = round(min(100.0, (current_val / target) * 100.0), 1) if target > 0 else 0.0
                    achieved = current_val >= target

            elif g_type == GoalType.MAX_POSTURE_RISK_EVENTS_PER_HOUR.value:
                current_val = overview.posture_events_per_valid_observation_hour
                if current_val is not None:
                    achieved = current_val <= target
                    progress = 100.0 if achieved else max(0.0, round((1.0 - (current_val - target) / target) * 100.0, 1))

            records.append(PersonalGoalRecord(
                id=g["id"],
                user_id=g["user_id"],
                goal_type=GoalType(g_type),
                target_value=target,
                created_at=g.get("created_at"),
                updated_at=g.get("updated_at"),
                current_value=current_val,
                progress_percentage=progress,
                achieved=achieved
            ))

        return records
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to list personal goals: {str(e)}"
        )


@router.put("", response_model=PersonalGoalRecord)
async def upsert_goal(
    payload: PersonalGoalCreate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    try:
        if payload.target_value <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="target_value must be greater than 0"
            )
        if payload.goal_type == GoalType.GOOD_POSTURE_PERCENTAGE and payload.target_value > 100.0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="target_value for GOOD_POSTURE_PERCENTAGE cannot exceed 100%"
            )

        data = {
            "id": str(uuid.uuid4()),
            "user_id": user.id,
            "goal_type": payload.goal_type.value,
            "target_value": payload.target_value,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        saved = await session_service.repository.upsert_goal(
            user_id=user.id, token=user.token, payload=data
        )
        if not saved:
            raise HTTPException(status_code=500, detail="Failed to persist goal")

        return PersonalGoalRecord(
            id=saved.get("id", data["id"]),
            user_id=user.id,
            goal_type=payload.goal_type,
            target_value=payload.target_value,
            created_at=saved.get("created_at"),
            updated_at=saved.get("updated_at")
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to upsert goal: {str(e)}"
        )


@router.delete("/{goal_id}", response_model=Dict[str, Any])
async def delete_goal(
    goal_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    try:
        success = await session_service.repository.delete_goal(goal_id=goal_id, token=user.token)
        if not success:
            raise HTTPException(status_code=404, detail="Goal not found or unauthorized")
        return {"status": "success", "deleted_goal_id": goal_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to delete goal: {str(e)}"
        )
