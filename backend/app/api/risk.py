"""VisionGuard Mission 05: Risk & Intervention REST API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.intelligence.risk_models import (
    RiskLevel,
    RiskCategory,
    RiskReasonCode,
    DomainRiskState,
    OverallRiskState,
)
from app.alerts.models import RiskEvent, Intervention
from app.perception.engine import get_perception_engine, PerceptionEngine

router = APIRouter(prefix="/risk", tags=["risk"])


def get_engine() -> PerceptionEngine:
    return get_perception_engine()


class RiskStatusResponse(BaseModel):
    risk_level: RiskLevel
    risk_score: Optional[float] = None
    posture_risk: DomainRiskState
    alertness_risk: DomainRiskState
    dominant_category: Optional[RiskCategory] = None
    active_reasons: List[RiskReasonCode] = []
    active_intervention: Optional[Intervention] = None
    confidence: float = 0.0


class RiskEventsResponse(BaseModel):
    events: List[RiskEvent]
    total_count: int


@router.get("/status", response_model=RiskStatusResponse, summary="Get current risk evaluation and active intervention")
async def get_risk_status(engine: PerceptionEngine = Depends(get_engine)):
    """Return the current temporal risk state across posture and alertness domains."""
    risk_state = engine.risk_engine.latest_state
    active_intervention = engine.intervention_engine.active_intervention
    return RiskStatusResponse(
        risk_level=risk_state.level,
        risk_score=risk_state.score,
        posture_risk=risk_state.posture_risk,
        alertness_risk=risk_state.alertness_risk,
        dominant_category=risk_state.dominant_category,
        active_reasons=risk_state.active_reasons,
        active_intervention=active_intervention,
        confidence=risk_state.confidence,
    )


@router.get("/events", response_model=RiskEventsResponse, summary="Get bounded risk event history")
async def get_risk_events(engine: PerceptionEngine = Depends(get_engine)):
    """Return in-memory bounded history of meaningful risk lifecycle events (STARTED, RESOLVED)."""
    events = engine.intervention_engine.event_history
    return RiskEventsResponse(
        events=events,
        total_count=len(events),
    )


@router.post("/events/reset", summary="Reset risk event history and alert cooldowns")
async def reset_risk_events(engine: PerceptionEngine = Depends(get_engine)):
    """Reset event history and alert rate-limiting cooldowns.

    Note: Does not modify ongoing physical risk states or perception baselines.
    """
    engine.intervention_engine.reset_history()
    return {
        "status": "RESET",
        "message": "Risk event history and alert cooldowns cleared.",
    }
