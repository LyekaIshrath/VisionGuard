from enum import Enum
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class CoverageLevel(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"

class ModalityCoverage(BaseModel):
    data_quality: CoverageLevel
    sessions_with_known_exposure: int

class CohortCoverage(BaseModel):
    sessions_total: int
    posture: ModalityCoverage
    alertness: ModalityCoverage

class AnalyticsOverview(BaseModel):
    total_monitored_seconds: float = 0.0
    total_sessions: int = 0
    good_posture_seconds: Optional[float] = None
    good_posture_percentage: Optional[float] = None
    posture_risk_seconds: Optional[float] = None
    alertness_risk_seconds: Optional[float] = None
    posture_events_per_valid_observation_hour: Optional[float] = None
    alertness_events_per_valid_observation_hour: Optional[float] = None
    average_posture_score: Optional[float] = None
    average_alertness_score: Optional[float] = None
    total_risk_events: int = 0
    total_interventions: int = 0
    coverage: CohortCoverage

class DailyTrendItem(BaseModel):
    date: str  # YYYY-MM-DD
    total_monitored_seconds: float = 0.0
    good_posture_seconds: float = 0.0
    valid_posture_seconds: Optional[float] = None
    good_posture_percentage: Optional[float] = None
    posture_events_per_valid_observation_hour: Optional[float] = None
    alertness_events_per_valid_observation_hour: Optional[float] = None
    average_posture_score: Optional[float] = None
    average_alertness_score: Optional[float] = None
    risk_event_count: int = 0
    intervention_count: int = 0
    coverage: CohortCoverage

class TimeOfDayBucket(BaseModel):
    bucket: str  # MORNING, AFTERNOON, EVENING, NIGHT
    label: str   # e.g., "Morning (06:00 - 12:00)"
    monitored_exposure_seconds: float = 0.0
    risk_event_count: int = 0
    events_per_monitored_hour: Optional[float] = None

class InsightType(str, Enum):
    POSITIVE_PATTERN = "POSITIVE_PATTERN"
    ATTENTION_PATTERN = "ATTENTION_PATTERN"
    INFORMATIONAL = "INFORMATIONAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

class Insight(BaseModel):
    id: str
    type: InsightType
    title: str
    description: str
    metric_reference: Optional[str] = None
    recommended_action: Optional[str] = None

class GoalType(str, Enum):
    DAILY_MONITORING_MINUTES = "DAILY_MONITORING_MINUTES"
    GOOD_POSTURE_PERCENTAGE = "GOOD_POSTURE_PERCENTAGE"
    MAX_POSTURE_RISK_EVENTS_PER_HOUR = "MAX_POSTURE_RISK_EVENTS_PER_HOUR"

class PersonalGoalCreate(BaseModel):
    goal_type: GoalType
    target_value: float

class PersonalGoalRecord(BaseModel):
    id: str
    user_id: str
    goal_type: GoalType
    target_value: float
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    current_value: Optional[float] = None
    progress_percentage: Optional[float] = None
    achieved: Optional[bool] = None
