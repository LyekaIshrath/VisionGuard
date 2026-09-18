"""Facial Geometry Layer for Alertness & Possible-Drowsiness Monitoring.

Extracts scale-invariant 2D normalized metrics from MediaPipe Face landmarks:
- Eye Aspect Ratio (EAR) for left, right, and robust combined eyes
- Mouth Opening Ratio (MOR) for yawn detection
- Head Drop / Pitch Proxy for posture/nod detection
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Dict, Any

from app.alertness.config import AlertnessConfig, DEFAULT_CONFIG


def _euclidean_dist(p1: Dict[str, float], p2: Dict[str, float]) -> float:
    """Calculate Euclidean distance between two normalized 2D points."""
    dx = p1.get("x", 0.0) - p2.get("x", 0.0)
    dy = p1.get("y", 0.0) - p2.get("y", 0.0)
    return math.sqrt(dx * dx + dy * dy)


def _is_valid_point(p: Optional[Dict[str, Any]]) -> bool:
    """Check if point exists with finite numeric coordinates."""
    if p is None or not isinstance(p, dict):
        return False
    x = p.get("x")
    y = p.get("y")
    if x is None or y is None:
        return False
    if math.isnan(x) or math.isinf(x) or math.isnan(y) or math.isinf(y):
        return False
    return True


@dataclass
class FaceGeometry:
    left_ear: Optional[float] = None
    right_ear: Optional[float] = None
    combined_ear: Optional[float] = None
    left_eye_valid: bool = False
    right_eye_valid: bool = False
    mouth_ratio: Optional[float] = None
    mouth_valid: bool = False
    head_pitch_ratio: Optional[float] = None
    head_valid: bool = False
    confidence: float = 0.0
    is_valid: bool = False


def extract_face_geometry(
    face_data: Optional[Dict[str, Any]],
    config: AlertnessConfig = DEFAULT_CONFIG,
) -> FaceGeometry:
    """Extract scale-invariant normalized geometric metrics from face landmarks.

    Guarantees:
    - Never raises ZeroDivisionError, NaN, or Inf.
    - Does NOT convert missing/invalid landmarks to closed eyes.
    - Evaluates left and right eyes independently before robust fusion.
    """
    if not face_data or not face_data.get("face_detected", False):
        return FaceGeometry()

    eye_landmarks = face_data.get("eye_landmarks", {})
    mouth_landmarks = face_data.get("mouth_landmarks", {})
    head_ref = face_data.get("head_reference", {})

    # --- Left Eye Openness (EAR) ---
    left_ear: Optional[float] = None
    left_valid: bool = False
    left_eye = eye_landmarks.get("left_eye")
    if isinstance(left_eye, dict):
        # Support either full multi-point or p1/p2 pairs
        outer = left_eye.get("outer") or left_eye.get("p1")
        inner = left_eye.get("inner") or left_eye.get("p2")
        top = left_eye.get("top")
        bottom = left_eye.get("bottom")
        top2 = left_eye.get("top2")
        bottom2 = left_eye.get("bottom2")

        if _is_valid_point(outer) and _is_valid_point(inner):
            w = _euclidean_dist(outer, inner)
            if w > 1e-4:
                v_dist = 0.0
                v_count = 0
                if _is_valid_point(top) and _is_valid_point(bottom):
                    v_dist += _euclidean_dist(top, bottom)
                    v_count += 1
                if _is_valid_point(top2) and _is_valid_point(bottom2):
                    v_dist += _euclidean_dist(top2, bottom2)
                    v_count += 1

                if v_count > 0:
                    ear_val = (v_dist / v_count) / w
                    if not (math.isnan(ear_val) or math.isinf(ear_val)):
                        if 0.0 <= ear_val <= 1.0:
                            left_ear = ear_val
                            left_valid = True

    # --- Right Eye Openness (EAR) ---
    right_ear: Optional[float] = None
    right_valid: bool = False
    right_eye = eye_landmarks.get("right_eye")
    if isinstance(right_eye, dict):
        outer = right_eye.get("outer") or right_eye.get("p1")
        inner = right_eye.get("inner") or right_eye.get("p2")
        top = right_eye.get("top")
        bottom = right_eye.get("bottom")
        top2 = right_eye.get("top2")
        bottom2 = right_eye.get("bottom2")

        if _is_valid_point(outer) and _is_valid_point(inner):
            w = _euclidean_dist(outer, inner)
            if w > 1e-4:
                v_dist = 0.0
                v_count = 0
                if _is_valid_point(top) and _is_valid_point(bottom):
                    v_dist += _euclidean_dist(top, bottom)
                    v_count += 1
                if _is_valid_point(top2) and _is_valid_point(bottom2):
                    v_dist += _euclidean_dist(top2, bottom2)
                    v_count += 1

                if v_count > 0:
                    ear_val = (v_dist / v_count) / w
                    if not (math.isnan(ear_val) or math.isinf(ear_val)):
                        if 0.0 <= ear_val <= 1.0:
                            right_ear = ear_val
                            right_valid = True

    # --- Robust Eye Fusion ---
    combined_ear: Optional[float] = None
    eye_confidence: float = 0.0

    if left_valid and right_valid:
        combined_ear = (left_ear + right_ear) / 2.0
        eye_confidence = 1.0
    elif left_valid:
        combined_ear = left_ear
        eye_confidence = 0.65  # Single eye reliable
    elif right_valid:
        combined_ear = right_ear
        eye_confidence = 0.65  # Single eye reliable
    else:
        combined_ear = None
        eye_confidence = 0.0

    # --- Mouth Opening Ratio (MOR) ---
    mouth_ratio: Optional[float] = None
    mouth_valid: bool = False
    if isinstance(mouth_landmarks, dict):
        top_lip = mouth_landmarks.get("top") or mouth_landmarks.get("p1")
        bottom_lip = mouth_landmarks.get("bottom") or mouth_landmarks.get("p2")
        left_corner = mouth_landmarks.get("left")
        right_corner = mouth_landmarks.get("right")

        if _is_valid_point(top_lip) and _is_valid_point(bottom_lip):
            v_mouth = _euclidean_dist(top_lip, bottom_lip)
            if _is_valid_point(left_corner) and _is_valid_point(right_corner):
                h_mouth = _euclidean_dist(left_corner, right_corner)
            else:
                h_mouth = 0.0

            if h_mouth > 1e-4:
                mor_val = v_mouth / h_mouth
            else:
                # Approximate normalization if horizontal mouth width unavailable
                mor_val = v_mouth * 4.0

            if not (math.isnan(mor_val) or math.isinf(mor_val)):
                mouth_ratio = mor_val
                mouth_valid = True

    # --- Head Drop / Pitch Proxy ---
    head_pitch_ratio: Optional[float] = None
    head_valid: bool = False
    if isinstance(head_ref, dict):
        forehead = head_ref.get("forehead")
        nose_tip = head_ref.get("nose_tip")
        chin = head_ref.get("chin")

        if _is_valid_point(nose_tip) and _is_valid_point(chin):
            if _is_valid_point(forehead):
                face_h = chin["y"] - forehead["y"]
                if face_h > 1e-3:
                    pitch_val = (nose_tip["y"] - forehead["y"]) / face_h
                    if not (math.isnan(pitch_val) or math.isinf(pitch_val)):
                        head_pitch_ratio = pitch_val
                        head_valid = True
            else:
                # Alternative vertical ratio between nose and chin
                dist_nc = abs(chin["y"] - nose_tip["y"])
                if not (math.isnan(dist_nc) or math.isinf(dist_nc)):
                    head_pitch_ratio = dist_nc
                    head_valid = True

    overall_valid = (left_valid or right_valid) and (eye_confidence > 0.0)

    return FaceGeometry(
        left_ear=left_ear,
        right_ear=right_ear,
        combined_ear=combined_ear,
        left_eye_valid=left_valid,
        right_eye_valid=right_valid,
        mouth_ratio=mouth_ratio,
        mouth_valid=mouth_valid,
        head_pitch_ratio=head_pitch_ratio,
        head_valid=head_valid,
        confidence=eye_confidence,
        is_valid=overall_valid,
    )
