import time
from typing import Optional, Dict, Any
from app.human_state.models import HumanState

class SessionAggregator:
    """
    Aggregates session metrics using monotonic time integration.
    Does not assume fixed 10 Hz sampling.
    Averages exclude UNKNOWN and uncalibrated values (they are never treated as 0).
    """
    def __init__(self, session_id: str, user_id: str):
        self.session_id = session_id
        self.user_id = user_id
        self.start_mono = time.monotonic()
        self.last_sample_mono: Optional[float] = None
        
        # Accumulators
        self.total_active_seconds: float = 0.0
        self.good_posture_seconds: float = 0.0
        self.posture_risk_seconds: float = 0.0
        self.alertness_risk_seconds: float = 0.0
        
        # Time-weighted scores (accumulated sum of score * dt)
        self.posture_score_weighted_sum: float = 0.0
        self.posture_valid_seconds: float = 0.0
        
        self.alertness_score_weighted_sum: float = 0.0
        self.alertness_valid_seconds: float = 0.0
        
        # Counts
        self.risk_event_count: int = 0
        self.intervention_count: int = 0

    def add_sample(self, state: HumanState, current_mono: Optional[float] = None) -> None:
        if current_mono is None:
            current_mono = time.monotonic()
            
        if self.last_sample_mono is None:
            dt = 0.0
        else:
            dt = current_mono - self.last_sample_mono
            # Clamp dt to maximum 1.0s to avoid skewing metrics after long pauses
            dt = max(0.0, min(dt, 1.0))
            
        self.last_sample_mono = current_mono
        self.total_active_seconds += dt
        
        # Posture metrics
        if state.posture_status == "GOOD":
            self.good_posture_seconds += dt
        elif state.posture_status == "NEEDS_ATTENTION":
            self.posture_risk_seconds += dt
            
        if (state.posture_score is not None and 
            state.posture_status not in ("UNKNOWN", "NOT_CALIBRATED", None)):
            self.posture_score_weighted_sum += state.posture_score * dt
            self.posture_valid_seconds += dt
            
        # Alertness metrics
        if state.alertness_status == "POSSIBLE_DROWSINESS":
            self.alertness_risk_seconds += dt
            
        if (state.alertness_score is not None and 
            state.alertness_status not in ("UNKNOWN", "NOT_CALIBRATED", None)):
            self.alertness_score_weighted_sum += state.alertness_score * dt
            self.alertness_valid_seconds += dt

    def record_risk_event(self) -> None:
        self.risk_event_count += 1

    def record_intervention(self) -> None:
        self.intervention_count += 1

    def get_summary(self) -> Dict[str, Any]:
        avg_posture = (
            round(self.posture_score_weighted_sum / self.posture_valid_seconds, 1)
            if self.posture_valid_seconds > 0 else None
        )
        avg_alertness = (
            round(self.alertness_score_weighted_sum / self.alertness_valid_seconds, 1)
            if self.alertness_valid_seconds > 0 else None
        )
        return {
            "duration_seconds": round(self.total_active_seconds, 1),
            "good_posture_seconds": round(self.good_posture_seconds, 1),
            "posture_risk_seconds": round(self.posture_risk_seconds, 1),
            "alertness_risk_seconds": round(self.alertness_risk_seconds, 1),
            "average_posture_score": avg_posture,
            "average_alertness_score": avg_alertness,
            "valid_posture_seconds": round(self.posture_valid_seconds, 1),
            "valid_alertness_seconds": round(self.alertness_valid_seconds, 1),
            "risk_event_count": self.risk_event_count,
            "intervention_count": self.intervention_count
        }
