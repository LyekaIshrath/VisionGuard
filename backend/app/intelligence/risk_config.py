"""VisionGuard Mission 05: Centralized Risk Configuration.

===============================================================================
INITIAL V1 ENGINEERING DEFAULTS — REQUIRES PHYSICAL VALIDATION
===============================================================================

All thresholds, accumulation rates, decay constants, hysteresis bounds,
cooldown durations, and stale evidence timeouts are centralized here.
Do NOT scatter magic constants through risk evaluation logic.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    """Centralized configuration for the Temporal Risk and Intervention Engines.

    All time intervals are in seconds and evaluated against monotonic clock.
    """

    # --- Posture Risk Temporal Accumulation & Decay ---
    # Duration of continuous non-GOOD posture before transitioning to MODERATE risk
    posture_warn_duration_sec: float = 8.0
    # Duration of continuous non-GOOD posture before transitioning to HIGH risk
    posture_high_duration_sec: float = 20.0
    # Rate of posture score risk decay when returning to GOOD posture (seconds to full decay)
    posture_recovery_time_sec: float = 4.0
    # Posture severity weight (combines posture score severity with duration)
    posture_severity_weight: float = 0.50
    posture_duration_weight: float = 0.50

    # --- Alertness Risk Temporal Accumulation & Decay ---
    # Duration of continuous POSSIBLE_DROWSINESS before transitioning to MODERATE risk
    alertness_warn_duration_sec: float = 1.5
    # Duration of continuous POSSIBLE_DROWSINESS before transitioning to HIGH risk
    alertness_high_duration_sec: float = 3.5
    # Rate of alertness risk decay when returning to sustained ALERT status
    alertness_recovery_time_sec: float = 3.0
    # Prolonged eye closure duration that independently triggers rapid HIGH alertness risk
    critical_eye_closure_sec: float = 2.0

    # --- Nonlinear Domain Risk Fusion ---
    # Dominant domain weight (overall risk strongly reflects the worst valid domain)
    dominant_domain_weight: float = 1.0
    # Cross-coupling coefficient: subtle contribution when BOTH domains are elevated
    # Must never cause two mild/low conditions to become HIGH
    cross_coupling_weight: float = 0.10

    # --- Temporal Hysteresis State Machine Bounds (0–100 scale) ---
    # Score thresholds for entering and exiting MODERATE risk
    hysteresis_moderate_entry: float = 40.0
    hysteresis_moderate_exit: float = 28.0
    # Score thresholds for entering and exiting HIGH risk
    hysteresis_high_entry: float = 70.0
    hysteresis_high_exit: float = 58.0
    # Minimum sustained duration at higher score before triggering level transition
    level_entry_sustain_sec: float = 1.0
    level_recovery_sustain_sec: float = 2.0

    # --- Observation Uncertainty & Stale Evidence Policy ---
    # Time without valid observation before previously frozen evidence is invalidated
    stale_observation_timeout_sec: float = 10.0

    # --- Intervention Rate-Limiting & Cooldowns ---
    # Cooldown between successive POSTURE interventions
    cooldown_posture_sec: float = 60.0
    # Cooldown between successive ALERTNESS interventions
    cooldown_alertness_sec: float = 30.0
    # Maximum number of historical risk events stored in in-memory ring buffer
    max_event_history_size: int = 100


DEFAULT_RISK_CONFIG = RiskConfig()
