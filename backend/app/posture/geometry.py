"""Normalized Body Geometry module for VisionGuard.

Extracts key body landmarks from MediaPipe Pose and calculates normalized 2D
geometric measurements and defensible proxies for posture analysis.

DISCLAIMER:
This module uses normalized 2D image coordinates to compute geometric proxies.
It does NOT measure true 3D spinal curvature, medical spinal alignment,
or true metric depth from monocular camera frames.

MIRRORING & ANATOMICAL CONVENTIONS:
MediaPipe Pose defines landmarks anatomically:
- 'left_shoulder' (idx 11) is the subject's anatomical left shoulder.
- 'right_shoulder' (idx 12) is the subject's anatomical right shoulder.
When facing a standard front-facing camera (unmirrored):
- The subject's left shoulder is on the viewer's right (larger x coordinate).
- The subject's right shoulder is on the viewer's left (smaller x coordinate).
To remain robust to camera mirroring or transformations, lateral displacement
is computed along the vector from right shoulder to left shoulder
(vector pointing towards anatomical left):
- A positive displacement indicates leaning towards the subject's anatomical LEFT.
- A negative displacement indicates leaning towards the subject's anatomical RIGHT.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


EPSILON = 1e-6
MIN_CONFIDENCE_THRESHOLD = 0.5


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float
    z: float = 0.0
    visibility: float = 1.0


@dataclass(frozen=True)
class BodyGeometry:
    """Normalized geometric measurements for a single frame."""
    shoulder_midpoint: Tuple[float, float]
    hip_midpoint: Tuple[float, float]
    head_reference: Tuple[float, float]
    shoulder_width: float
    torso_length: float
    shoulder_tilt: float
    head_lateral_displacement: float
    torso_lateral_displacement: float
    head_shoulder_vertical_ratio: float
    slouch_proxy: float
    forward_lean_proxy: float
    confidence: float
    has_hips: bool = True


def extract_body_geometry(
    landmarks: Dict[str, Any],
    min_confidence: float = MIN_CONFIDENCE_THRESHOLD,
) -> Optional[BodyGeometry]:
    """Extract and normalize body geometry from key landmark dictionary.

    Required landmarks:
      - 'nose'
      - 'left_shoulder'
      - 'right_shoulder'
    Optional (with fallback if missing/occluded):
      - 'left_ear', 'right_ear' (used for head reference)
      - 'left_hip', 'right_hip' (used for torso length and hip midpoint)

    Returns:
      BodyGeometry instance if valid, or None if landmarks are missing,
      low confidence, degenerate, or contain NaN/Inf.
    """
    if not landmarks or not isinstance(landmarks, dict):
        return None

    # Check required landmarks
    for name in ('nose', 'left_shoulder', 'right_shoulder'):
        if name not in landmarks or landmarks[name] is None:
            return None

    def parse_point(data: Any) -> Optional[Point2D]:
        if data is None or not isinstance(data, dict):
            return None
        x = data.get('x')
        y = data.get('y')
        z = data.get('z', 0.0)
        vis = data.get('visibility', 1.0)
        if x is None or y is None:
            return None
        try:
            x_f = float(x)
            y_f = float(y)
            z_f = float(z) if z is not None else 0.0
            vis_f = float(vis) if vis is not None else 1.0
        except (ValueError, TypeError):
            return None

        # Protect against NaN/Inf
        if math.isnan(x_f) or math.isinf(x_f) or math.isnan(y_f) or math.isinf(y_f):
            return None
        if math.isnan(z_f) or math.isinf(z_f):
            z_f = 0.0
        if math.isnan(vis_f) or math.isinf(vis_f):
            vis_f = 0.0
        return Point2D(x=x_f, y=y_f, z=z_f, visibility=vis_f)

    nose = parse_point(landmarks.get('nose'))
    l_shoulder = parse_point(landmarks.get('left_shoulder'))
    r_shoulder = parse_point(landmarks.get('right_shoulder'))

    if nose is None or l_shoulder is None or r_shoulder is None:
        return None

    if (
        nose.visibility < min_confidence
        or l_shoulder.visibility < min_confidence
        or r_shoulder.visibility < min_confidence
    ):
        return None

    # Check ears
    l_ear = parse_point(landmarks.get('left_ear'))
    r_ear = parse_point(landmarks.get('right_ear'))

    # Check hips
    l_hip = parse_point(landmarks.get('left_hip'))
    r_hip = parse_point(landmarks.get('right_hip'))

    # Shoulder width: 2D Euclidean distance between shoulders
    dx_s = l_shoulder.x - r_shoulder.x
    dy_s = l_shoulder.y - r_shoulder.y
    shoulder_width = math.sqrt(dx_s * dx_s + dy_s * dy_s)

    # Protect against degenerate geometry / zero division
    if shoulder_width < EPSILON:
        return None

    # Shoulder midpoint
    s_mid_x = (l_shoulder.x + r_shoulder.x) / 2.0
    s_mid_y = (l_shoulder.y + r_shoulder.y) / 2.0

    # Head reference: midpoint of ears if both visible, else nose, or blend
    if (
        l_ear is not None
        and r_ear is not None
        and l_ear.visibility >= min_confidence
        and r_ear.visibility >= min_confidence
    ):
        ear_mid_x = (l_ear.x + r_ear.x) / 2.0
        ear_mid_y = (l_ear.y + r_ear.y) / 2.0
        head_x = (ear_mid_x + nose.x) / 2.0
        head_y = (ear_mid_y + nose.y) / 2.0
    else:
        head_x = nose.x
        head_y = nose.y

    # Hip midpoint & torso length
    has_hips = False
    if (
        l_hip is not None
        and r_hip is not None
        and l_hip.visibility >= min_confidence
        and r_hip.visibility >= min_confidence
    ):
        h_mid_x = (l_hip.x + r_hip.x) / 2.0
        h_mid_y = (l_hip.y + r_hip.y) / 2.0
        dx_t = s_mid_x - h_mid_x
        dy_t = s_mid_y - h_mid_y
        torso_len = math.sqrt(dx_t * dx_t + dy_t * dy_t)
        if torso_len >= EPSILON:
            torso_length = torso_len
            has_hips = True
        else:
            torso_length = shoulder_width * 1.2
            h_mid_x, h_mid_y = s_mid_x, s_mid_y + torso_length
    else:
        # Fallback torso length estimated from shoulder width for upper-body framing
        torso_length = shoulder_width * 1.2
        h_mid_x = s_mid_x
        h_mid_y = s_mid_y + torso_length

    # Shoulder tilt: vertical difference normalized by shoulder width
    shoulder_tilt = dy_s / shoulder_width

    # Head lateral displacement:
    # Projection along shoulder axis from right to left shoulder
    unit_s_x = dx_s / shoulder_width
    unit_s_y = dy_s / shoulder_width
    offset_h_x = head_x - s_mid_x
    offset_h_y = head_y - s_mid_y
    head_lateral_displacement = (offset_h_x * unit_s_x + offset_h_y * unit_s_y) / shoulder_width

    # Torso lateral displacement:
    offset_t_x = s_mid_x - h_mid_x
    offset_t_y = s_mid_y - h_mid_y
    denom_t = torso_length if torso_length > EPSILON else shoulder_width
    torso_lateral_displacement = (offset_t_x * unit_s_x + offset_t_y * unit_s_y) / denom_t

    # Head/shoulder vertical relationship (y increases downwards in image space):
    # (s_mid_y - head_y) is positive when head is above shoulder midpoint
    head_shoulder_vertical = (s_mid_y - head_y) / shoulder_width

    # Slouch proxy:
    # In an upright posture, the head sits high above the shoulders.
    # When slouching, neck compresses and head drops towards shoulder line.
    slouch_proxy = head_shoulder_vertical

    # Forward-lean proxy:
    # In monocular 2D perspective, apparent shoulder width / torso length ratio
    forward_lean_proxy = shoulder_width / torso_length

    # Aggregate confidence
    confs = [nose.visibility, l_shoulder.visibility, r_shoulder.visibility]
    if l_ear and r_ear and l_ear.visibility >= min_confidence and r_ear.visibility >= min_confidence:
        confs.extend([l_ear.visibility, r_ear.visibility])
    if has_hips and l_hip and r_hip:
        confs.extend([l_hip.visibility, r_hip.visibility])
    avg_confidence = sum(confs) / len(confs)

    return BodyGeometry(
        shoulder_midpoint=(round(s_mid_x, 5), round(s_mid_y, 5)),
        hip_midpoint=(round(h_mid_x, 5), round(h_mid_y, 5)),
        head_reference=(round(head_x, 5), round(head_y, 5)),
        shoulder_width=round(shoulder_width, 5),
        torso_length=round(torso_length, 5),
        shoulder_tilt=round(shoulder_tilt, 5),
        head_lateral_displacement=round(head_lateral_displacement, 5),
        torso_lateral_displacement=round(torso_lateral_displacement, 5),
        head_shoulder_vertical_ratio=round(head_shoulder_vertical, 5),
        slouch_proxy=round(slouch_proxy, 5),
        forward_lean_proxy=round(forward_lean_proxy, 5),
        confidence=round(avg_confidence, 4),
        has_hips=has_hips,
    )
