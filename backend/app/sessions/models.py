from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class SessionCreate(BaseModel):
    device_name: Optional[str] = "VisionGuard Desktop"

class SessionUpdate(BaseModel):
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    good_posture_seconds: Optional[float] = None
    posture_risk_seconds: Optional[float] = None
    alertness_risk_seconds: Optional[float] = None
    average_posture_score: Optional[float] = None
    average_alertness_score: Optional[float] = None
    risk_event_count: Optional[int] = None
    intervention_count: Optional[int] = None
    status: Optional[str] = "COMPLETED"

class SessionRecord(BaseModel):
    id: str
    user_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    good_posture_seconds: float = 0.0
    posture_risk_seconds: float = 0.0
    alertness_risk_seconds: float = 0.0
    average_posture_score: Optional[float] = None
    average_alertness_score: Optional[float] = None
    risk_event_count: int = 0
    intervention_count: int = 0
    status: str = "ACTIVE"
    device_name: Optional[str] = "VisionGuard Desktop"

class RiskEventRecord(BaseModel):
    id: str
    session_id: Optional[str] = None
    user_id: str
    timestamp: datetime
    monotonic_timestamp: float
    category: str
    severity: str
    reason: str
    lifecycle: str = "STARTED"
    duration_seconds: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

class AnalyticsSummary(BaseModel):
    total_sessions: int = 0
    total_monitored_seconds: float = 0.0
    total_good_posture_seconds: float = 0.0
    good_posture_percentage: float = 0.0
    average_posture_score: Optional[float] = None
    average_alertness_score: Optional[float] = None
    total_risk_events: int = 0
    total_interventions: int = 0
    moderate_risk_count: int = 0
    high_risk_count: int = 0

class CloudStatusResponse(BaseModel):
    status: str
    configured: bool
    cloud_session_id: Optional[str] = None
    local_session_id: Optional[str] = None
    message: str
