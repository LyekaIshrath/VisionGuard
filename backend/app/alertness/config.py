"""Alertness Configuration & Engineering Defaults.

INITIAL V1 DEFAULTS — REQUIRES PHYSICAL CALIBRATION.
All thresholds here are centralized engineering defaults.
Personal calibration remains authoritative at runtime.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AlertnessConfig:
    # --- Eye Geometry & Closure Thresholds ---
    # Fraction of calibrated open-eye baseline below which eyes are considered closed
    ear_closure_ratio: float = 0.70

    # Geometric sanity limits for normalized Eye Aspect Ratio (EAR)
    ear_min_valid: float = 0.04
    ear_max_valid: float = 0.65

    # --- Blink Detection ---
    # Minimum and maximum duration for an eye closure to be classified as a normal blink
    blink_min_duration_sec: float = 0.05
    blink_max_duration_sec: float = 0.40

    # Minimum valid observation time before exposing blinks/min rate
    blink_rate_min_observation_sec: float = 15.0

    # --- PERCLOS-like Temporal Proxy ---
    # Rolling observation time window in seconds
    perclos_window_sec: float = 30.0

    # PERCLOS proxy fraction representing high drowsiness evidence
    perclos_drowsy_threshold: float = 0.15

    # --- Sustained Eye Closure ---
    # Duration of continuous eye closure to begin generating elevated drowsiness evidence
    sustained_closure_warn_sec: float = 1.0
    sustained_closure_critical_sec: float = 2.0

    # --- Mouth & Yawn Signal ---
    # Multiplier over calibrated resting mouth ratio to detect wide opening
    mor_yawn_multiplier: float = 2.0
    mor_yawn_min_absolute: float = 0.45

    # Minimum sustained duration for wide mouth opening to count as yawn
    yawn_min_duration_sec: float = 1.5
    yawn_window_sec: float = 120.0

    # --- Head Nod / Drop Proxy ---
    # Downward pitch displacement offset from calibrated baseline
    head_nod_pitch_offset: float = 0.10
    head_nod_min_duration_sec: float = 1.0

    # --- Evidence Fusion Weights ---
    weight_sustained_closure: float = 0.45
    weight_perclos: float = 0.30
    weight_yawn: float = 0.15
    weight_head_nod: float = 0.10

    # --- Hysteresis & State Transitions ---
    # Evidence score threshold to enter POSSIBLE_DROWSINESS
    evidence_entry_threshold: float = 0.55

    # Evidence score threshold to recover to ALERT
    evidence_recovery_threshold: float = 0.30

    # Continuous open-eye duration required before recovery is granted
    recovery_open_time_sec: float = 2.0

    # --- Calibration Parameters ---
    calibration_required_samples: int = 40
    # Discard bottom percentile of EAR samples during calibration to reject blinks
    calibration_blink_discard_percentile: float = 25.0
    # Maximum coefficient of variation of the open-eye samples to accept calibration
    calibration_max_ear_cv: float = 0.30


DEFAULT_CONFIG = AlertnessConfig()
