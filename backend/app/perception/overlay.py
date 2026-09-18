"""VisionGuard Live Landmark & Skeleton Overlay Renderer.

Draws real pose and face landmarks and derived reference geometry directly
onto preview video frames using OpenCV.

Guarantees:
- Pure visualization layer; never alters perception, calculations, or calibration.
- Uses existing MediaPipe inference results from the single perception pipeline.
- Never fabricates missing or low-confidence landmarks.
- Renders strictly in-memory; zero disk persistence.
"""

from __future__ import annotations

import math
from typing import Optional, Dict, Any, Tuple, List
import cv2
import numpy as np

# BGR color palette matching VisionGuard design system
from enum import Enum


class OverlayMode(str, Enum):
    OFF = "OFF"
    MINIMAL = "MINIMAL"
    DEBUG = "DEBUG"

    @classmethod
    def from_str(cls, val: Optional[str]) -> OverlayMode:
        if not val:
            return cls.MINIMAL
        upper = val.strip().upper()
        if upper == "OFF":
            return cls.OFF
        elif upper == "DEBUG":
            return cls.DEBUG
        return cls.MINIMAL


COLOR_ACCENT = (248, 189, 56)      # Sky Blue (#38bdf8 in BGR)
COLOR_GOOD = (129, 185, 16)        # Emerald Green (#10b981 in BGR)
COLOR_WARNING = (11, 158, 245)     # Amber (#f59e0b in BGR)
COLOR_HIGH = (68, 68, 239)         # Coral Red (#ef4444 in BGR)
COLOR_MUTED = (139, 116, 100)      # Muted Slate (#64748b in BGR)
COLOR_WHITE = (245, 245, 245)
COLOR_TORSO = (235, 200, 50)       # Distinctive Torso Reference Line


def _to_pixel(point: Optional[Dict[str, Any]], width: int, height: int) -> Optional[Tuple[int, int]]:
    """Safely convert normalized coordinates to pixel coordinates."""
    if point is None or not isinstance(point, dict):
        return None
    x = point.get("x")
    y = point.get("y")
    if x is None or y is None:
        return None
    try:
        x_f = float(x)
        y_f = float(y)
        if math.isnan(x_f) or math.isinf(x_f) or math.isnan(y_f) or math.isinf(y_f):
            return None
        # Reject out-of-bounds normalized coordinates (< 0.0 or > 1.0)
        if not (0.0 <= x_f <= 1.0 and 0.0 <= y_f <= 1.0):
            return None
        # Reject low-visibility landmarks if visibility metric is present
        vis = point.get("visibility")
        if vis is not None:
            vis_f = float(vis)
            if math.isnan(vis_f) or vis_f < 0.3:
                return None
        px = max(0, min(width - 1, int(round(x_f * width))))
        py = max(0, min(height - 1, int(round(y_f * height))))
        return (px, py)
    except Exception:
        return None


def _draw_node(img: np.ndarray, pt: Tuple[int, int], color: Tuple[int, int, int] = COLOR_ACCENT, radius: int = 3) -> None:
    """Draw small circular landmark node with subtle outline."""
    cv2.circle(img, pt, radius + 1, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.circle(img, pt, radius, color, -1, cv2.LINE_AA)


def _draw_connection(img: np.ndarray, pt1: Optional[Tuple[int, int]], pt2: Optional[Tuple[int, int]], color: Tuple[int, int, int] = COLOR_ACCENT, thickness: int = 1) -> None:
    """Draw connection line between two valid pixel points."""
    if pt1 is not None and pt2 is not None:
        cv2.line(img, pt1, pt2, color, thickness, cv2.LINE_AA)


class OverlayRenderer:
    """Real-time in-memory overlay renderer for VisionGuard preview."""

    @staticmethod
    def render(
        frame: np.ndarray,
        mode: str = "MINIMAL",
        pose_data: Optional[Dict[str, Any]] = None,
        face_data: Optional[Dict[str, Any]] = None,
        human_state: Optional[Any] = None,
        posture_geom: Optional[Any] = None,
        face_geom: Optional[Any] = None,
        posture_res: Optional[Any] = None,
        alertness_res: Optional[Any] = None,
        posture_baseline: Optional[Any] = None,
        alertness_baseline: Optional[Any] = None,
    ) -> np.ndarray:
        """Render landmark skeleton and telemetry overlay onto a copy of frame.

        Args:
            frame: BGR numpy image (e.g. 640x480).
            mode: 'OFF', 'MINIMAL', or 'DEBUG'.
        """
        if mode == "OFF" or frame is None:
            return frame

        canvas = frame.copy()
        height, width = canvas.shape[:2]

        # 1. Pose & Posture Skeleton Overlay
        if pose_data and pose_data.get("pose_detected", False):
            landmarks = pose_data.get("landmarks", {})
            OverlayRenderer._render_pose_skeleton(canvas, landmarks, width, height)

        # 2. Face & Alertness Geometry Overlay
        if face_data and face_data.get("face_detected", False):
            OverlayRenderer._render_face_geometry(canvas, face_data, width, height)

        # 3. Telemetry Overlay Badges (MINIMAL vs DEBUG)
        if mode == "DEBUG":
            OverlayRenderer._render_debug_telemetry(
                canvas,
                human_state=human_state,
                posture_geom=posture_geom,
                face_geom=face_geom,
                posture_res=posture_res,
                alertness_res=alertness_res,
                posture_baseline=posture_baseline,
                alertness_baseline=alertness_baseline,
                width=width,
                height=height,
            )
        else:
            # MINIMAL mode
            OverlayRenderer._render_minimal_badges(
                canvas,
                human_state=human_state,
                width=width,
                height=height,
            )

        return canvas

    @staticmethod
    def _render_pose_skeleton(canvas: np.ndarray, landmarks: Dict[str, Any], width: int, height: int) -> None:
        """Draw real posture landmarks: nose, ears, shoulders, hips, and torso line."""
        pt_nose = _to_pixel(landmarks.get("nose"), width, height)
        pt_l_ear = _to_pixel(landmarks.get("left_ear"), width, height)
        pt_r_ear = _to_pixel(landmarks.get("right_ear"), width, height)
        pt_l_sh = _to_pixel(landmarks.get("left_shoulder"), width, height)
        pt_r_sh = _to_pixel(landmarks.get("right_shoulder"), width, height)
        pt_l_hip = _to_pixel(landmarks.get("left_hip"), width, height)
        pt_r_hip = _to_pixel(landmarks.get("right_hip"), width, height)

        # Connections: Head
        _draw_connection(canvas, pt_l_ear, pt_nose, COLOR_ACCENT, 1)
        _draw_connection(canvas, pt_nose, pt_r_ear, COLOR_ACCENT, 1)

        # Connections: Upper Torso / Shoulder Axis
        _draw_connection(canvas, pt_l_sh, pt_r_sh, COLOR_ACCENT, 2)

        # Connections: Torso Sides
        _draw_connection(canvas, pt_l_sh, pt_l_hip, COLOR_ACCENT, 1)
        _draw_connection(canvas, pt_r_sh, pt_r_hip, COLOR_ACCENT, 1)

        # Connections: Hip Axis
        _draw_connection(canvas, pt_l_hip, pt_r_hip, COLOR_ACCENT, 1)

        # Derived Reference Geometry: Shoulder Midpoint & Hip Midpoint
        pt_sh_mid = None
        if pt_l_sh and pt_r_sh:
            pt_sh_mid = ((pt_l_sh[0] + pt_r_sh[0]) // 2, (pt_l_sh[1] + pt_r_sh[1]) // 2)

        pt_hip_mid = None
        if pt_l_hip and pt_r_hip:
            pt_hip_mid = ((pt_l_hip[0] + pt_r_hip[0]) // 2, (pt_l_hip[1] + pt_r_hip[1]) // 2)

        # Connect Torso Center Line (Shoulder Midpoint -> Hip Midpoint)
        if pt_sh_mid and pt_hip_mid:
            _draw_connection(canvas, pt_sh_mid, pt_hip_mid, COLOR_TORSO, 2)
            _draw_node(canvas, pt_sh_mid, COLOR_TORSO, radius=4)
            _draw_node(canvas, pt_hip_mid, COLOR_TORSO, radius=4)

        # Draw primary landmark nodes
        for pt in (pt_nose, pt_l_ear, pt_r_ear, pt_l_sh, pt_r_sh, pt_l_hip, pt_r_hip):
            if pt is not None:
                _draw_node(canvas, pt, COLOR_ACCENT, radius=3)

    @staticmethod
    def _render_face_geometry(canvas: np.ndarray, face_data: Dict[str, Any], width: int, height: int) -> None:
        """Draw real alertness landmarks: eyes, mouth, and head reference axis."""
        eyes = face_data.get("eye_landmarks", {})
        m_raw = face_data.get("mouth_landmarks", {})
        mouth = m_raw.get("mouth", m_raw) if isinstance(m_raw, dict) else {}
        head = face_data.get("head_reference", {})

        # 1. Left Eye
        l_eye = eyes.get("left_eye", {})
        l_outer = _to_pixel(l_eye.get("outer") or l_eye.get("p1"), width, height)
        l_inner = _to_pixel(l_eye.get("inner") or l_eye.get("p2"), width, height)
        l_top = _to_pixel(l_eye.get("top"), width, height)
        l_bottom = _to_pixel(l_eye.get("bottom"), width, height)
        l_top2 = _to_pixel(l_eye.get("top2"), width, height)
        l_bottom2 = _to_pixel(l_eye.get("bottom2"), width, height)

        if l_outer and l_inner and l_top and l_bottom:
            # Eye outline polygon
            pts_l = [p for p in (l_outer, l_top2, l_top, l_inner, l_bottom, l_bottom2) if p is not None]
            for i in range(len(pts_l)):
                _draw_connection(canvas, pts_l[i], pts_l[(i + 1) % len(pts_l)], COLOR_GOOD, 1)
            # Vertical eye openness segment
            _draw_connection(canvas, l_top, l_bottom, COLOR_WARNING, 1)
            for p in (l_outer, l_inner, l_top, l_bottom):
                _draw_node(canvas, p, COLOR_GOOD, radius=2)

        # 2. Right Eye
        r_eye = eyes.get("right_eye", {})
        r_outer = _to_pixel(r_eye.get("outer") or r_eye.get("p1"), width, height)
        r_inner = _to_pixel(r_eye.get("inner") or r_eye.get("p2"), width, height)
        r_top = _to_pixel(r_eye.get("top"), width, height)
        r_bottom = _to_pixel(r_eye.get("bottom"), width, height)
        r_top2 = _to_pixel(r_eye.get("top2"), width, height)
        r_bottom2 = _to_pixel(r_eye.get("bottom2"), width, height)

        if r_outer and r_inner and r_top and r_bottom:
            pts_r = [p for p in (r_outer, r_top2, r_top, r_inner, r_bottom, r_bottom2) if p is not None]
            for i in range(len(pts_r)):
                _draw_connection(canvas, pts_r[i], pts_r[(i + 1) % len(pts_r)], COLOR_GOOD, 1)
            # Vertical eye openness segment
            _draw_connection(canvas, r_top, r_bottom, COLOR_WARNING, 1)
            for p in (r_outer, r_inner, r_top, r_bottom):
                _draw_node(canvas, p, COLOR_GOOD, radius=2)

        # 3. Mouth
        m_top = _to_pixel(mouth.get("top") or mouth.get("p1"), width, height)
        m_bottom = _to_pixel(mouth.get("bottom") or mouth.get("p2"), width, height)
        m_left = _to_pixel(mouth.get("left"), width, height)
        m_right = _to_pixel(mouth.get("right"), width, height)

        if m_top and m_bottom and m_left and m_right:
            _draw_connection(canvas, m_left, m_top, COLOR_ACCENT, 1)
            _draw_connection(canvas, m_top, m_right, COLOR_ACCENT, 1)
            _draw_connection(canvas, m_right, m_bottom, COLOR_ACCENT, 1)
            _draw_connection(canvas, m_bottom, m_left, COLOR_ACCENT, 1)
            # Vertical opening line
            _draw_connection(canvas, m_top, m_bottom, COLOR_WARNING, 1)
            for p in (m_left, m_right, m_top, m_bottom):
                _draw_node(canvas, p, COLOR_ACCENT, radius=2)

        # 4. Head Reference Line
        pt_forehead = _to_pixel(head.get("forehead"), width, height)
        pt_nose_tip = _to_pixel(head.get("nose_tip"), width, height)
        pt_chin = _to_pixel(head.get("chin"), width, height)

        if pt_forehead and pt_nose_tip:
            _draw_connection(canvas, pt_forehead, pt_nose_tip, COLOR_MUTED, 1)
        if pt_nose_tip and pt_chin:
            _draw_connection(canvas, pt_nose_tip, pt_chin, COLOR_MUTED, 1)

    @staticmethod
    def _render_minimal_badges(canvas: np.ndarray, human_state: Optional[Any], width: int, height: int) -> None:
        """Draw clean, unobtrusive telemetry badges in corners."""
        if human_state is None:
            return

        posture = human_state.posture_status or "NOT_CALIBRATED"
        alertness = human_state.alertness_status or "NOT_CALIBRATED"
        eye_state = human_state.eye_state or "UNKNOWN"
        closure_sec = human_state.eye_closure_duration or 0.0

        p_color = COLOR_GOOD if posture == "GOOD" else COLOR_WARNING if posture in ("SLOUCHING", "FORWARD_LEAN", "LEFT_LEAN", "RIGHT_LEAN") else COLOR_MUTED
        a_color = COLOR_GOOD if alertness == "ALERT" else COLOR_HIGH if alertness == "POSSIBLE_DROWSINESS" else COLOR_MUTED

        # Semi-transparent top-right info box
        box_w = 210
        box_h = 58
        x1 = width - box_w - 12
        y1 = 12

        sub_img = canvas[y1:y1 + box_h, x1:x1 + box_w]
        dark_rect = np.zeros(sub_img.shape, dtype=np.uint8)
        cv2.addWeighted(sub_img, 0.35, dark_rect, 0.65, 0, sub_img)

        # Border
        cv2.rectangle(canvas, (x1, y1), (x1 + box_w, y1 + box_h), (50, 65, 85), 1)

        # Text 1: Posture Status
        cv2.putText(canvas, f"POSTURE: {posture}", (x1 + 8, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, p_color, 1, cv2.LINE_AA)

        # Text 2: Alertness Status & Eyes
        eye_text = f"ALERTNESS: {alertness} | {eye_state}"
        if closure_sec > 0.5:
            eye_text += f" ({closure_sec:.1f}s)"
        cv2.putText(canvas, eye_text, (x1 + 8, y1 + 44), cv2.FONT_HERSHEY_SIMPLEX, 0.40, a_color, 1, cv2.LINE_AA)

    @staticmethod
    def _render_debug_telemetry(
        canvas: np.ndarray,
        human_state: Optional[Any],
        posture_geom: Optional[Any],
        face_geom: Optional[Any],
        posture_res: Optional[Any],
        alertness_res: Optional[Any],
        posture_baseline: Optional[Any],
        alertness_baseline: Optional[Any],
        width: int,
        height: int,
    ) -> None:
        """Render detailed derived metrics overlay for engineering inspection."""
        p_status = human_state.posture_status if human_state else "UNKNOWN"
        p_score = human_state.posture_score if human_state else None
        a_status = human_state.alertness_status if human_state else "UNKNOWN"
        a_score = human_state.alertness_score if human_state else None
        risk_lvl = human_state.risk_level if human_state else "UNKNOWN"
        risk_sc = human_state.risk_score if human_state else None
        closure = human_state.eye_closure_duration if human_state else 0.0

        ear_val = face_geom.combined_ear if face_geom else None
        ear_thresh = alertness_baseline.closed_eye_threshold if alertness_baseline else None
        mor_val = face_geom.mouth_ratio if face_geom else None
        mor_thresh = alertness_baseline.yawn_threshold if alertness_baseline else None

        ear_str = f"{ear_val:.3f}" if ear_val is not None else "-"
        ear_th_str = f"{ear_thresh:.3f}" if ear_thresh is not None else "-"
        mor_str = f"{mor_val:.3f}" if mor_val is not None else "-"
        mor_th_str = f"{mor_thresh:.2f}" if mor_thresh is not None else "-"
        closure_str = f"{closure:.2f}s" if isinstance(closure, (int, float)) else "-"
        p_sc_str = f"{p_score:.1f}" if isinstance(p_score, (int, float)) else "-"
        a_sc_str = f"{a_score:.1f}" if isinstance(a_score, (int, float)) else "-"
        r_sc_str = f"{risk_sc:.1f}" if isinstance(risk_sc, (int, float)) else "-"

        lines = [
            "DEBUG TELEMETRY (LIVE)",
            f"Posture: {p_status} (Score: {p_sc_str})",
            f"Alertness: {a_status} (Score: {a_sc_str})",
            f"EAR: {ear_str} (Thresh: {ear_th_str})",
            f"Closure: {closure_str}",
            f"MOR: {mor_str} (Thresh: {mor_th_str})",
            f"Risk: {risk_lvl} ({r_sc_str})",
        ]

        box_w = 260
        box_h = len(lines) * 20 + 16
        x1 = width - box_w - 12
        y1 = 12

        sub_img = canvas[y1:y1 + box_h, x1:x1 + box_w]
        dark_rect = np.zeros(sub_img.shape, dtype=np.uint8)
        cv2.addWeighted(sub_img, 0.25, dark_rect, 0.75, 0, sub_img)
        cv2.rectangle(canvas, (x1, y1), (x1 + box_w, y1 + box_h), (56, 189, 248), 1)

        y_offset = y1 + 20
        for i, text in enumerate(lines):
            color = COLOR_ACCENT if i == 0 else COLOR_WHITE
            cv2.putText(canvas, text, (x1 + 10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1, cv2.LINE_AA)
            y_offset += 20
