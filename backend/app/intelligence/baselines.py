"""VisionGuard General Built-In Engineering Default Baselines.

Provides robust, empirical default baselines for posture and alertness
without requiring manual user calibration.

Priority:
  1. PERSONALIZED (if user explicitly performed calibration)
  2. BUILT_IN (immediate out-of-the-box engineering default)

NOTE: These values are initial engineering defaults for standard desktop
workstation ergonomics (50-70 cm viewing distance) and are not clinical
or diagnostic criteria.
"""

from typing import Tuple, Optional
from app.posture.calibration import PostureBaseline
from app.alertness.calibration import AlertnessBaseline

# Built-in empirical defaults for desktop posture geometry
BUILT_IN_POSTURE_BASELINE = PostureBaseline(
    shoulder_width=0.35,
    torso_length=0.48,
    shoulder_tilt=0.0,
    head_lateral_displacement=0.0,
    torso_lateral_displacement=0.0,
    head_shoulder_vertical_ratio=0.28,
    slouch_proxy=0.28,
    forward_lean_proxy=0.35,
    confidence=0.85,
    quality="BUILT_IN_DEFAULT",
    sample_count=0,
    has_hips=True,
)

# Built-in empirical defaults for open-eye wakefulness geometry
BUILT_IN_ALERTNESS_BASELINE = AlertnessBaseline(
    open_eye_ear=0.260,
    closed_eye_threshold=0.180,
    mouth_mor=0.150,
    yawn_threshold=0.550,
    head_pitch_ratio=0.0,
    head_nod_threshold=-0.140,
    samples_count=0,
    quality="BUILT_IN_DEFAULT",
)

def get_effective_posture_baseline(
    personalized_baseline: Optional[PostureBaseline] = None
) -> Tuple[PostureBaseline, str, float]:
    """Return (effective_baseline, baseline_source, baseline_confidence)."""
    if personalized_baseline is not None:
        return personalized_baseline, "PERSONALIZED", personalized_baseline.confidence
    return BUILT_IN_POSTURE_BASELINE, "BUILT_IN", 0.85

def get_effective_alertness_baseline(
    personalized_baseline: Optional[AlertnessBaseline] = None
) -> Tuple[AlertnessBaseline, str, float]:
    """Return (effective_baseline, baseline_source, baseline_confidence)."""
    if personalized_baseline is not None:
        return personalized_baseline, "PERSONALIZED", 0.95
    return BUILT_IN_ALERTNESS_BASELINE, "BUILT_IN", 0.85
