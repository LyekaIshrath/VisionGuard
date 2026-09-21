"""VisionGuard Live Landmark & Skeleton Overlay Renderer.

Draws real pose and face landmarks and derived reference geometry directly
onto preview video frames using OpenCV.

Guarantees:
- Pure visualization layer; never alters perception, calculations, or calibration.
- Uses existing MediaPipe inference results from the single perception pipeline.
- Never fabricates missing or low-confidence landmarks.
- Renders strictly in-memory; zero disk persistence.
- Reuses 1 FaceLandmarker and 1 PoseLandmarker (NO SECOND INFERENCE).
"""

from __future__ import annotations

import math
from typing import Optional, Dict, Any, Tuple, List
import cv2
import numpy as np
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


COLOR_ACCENT = (248, 189, 56)       # Sky Blue (#38bdf8 in BGR)
COLOR_GOOD = (129, 185, 16)         # Emerald Green (#10b981 in BGR)
COLOR_WARNING = (11, 158, 245)      # Amber (#f59e0b in BGR)
COLOR_HIGH = (68, 68, 239)          # Coral Red (#ef4444 in BGR)
COLOR_MUTED = (139, 116, 100)       # Muted Slate (#64748b in BGR)
COLOR_WHITE = (245, 245, 245)
COLOR_TORSO = (235, 200, 50)        # Torso Reference Line (BGR)
COLOR_VERT_AXIS = (217, 70, 239)    # Fuchsia / Magenta Vertical Reference Axis (#ef46d9 in BGR)
COLOR_HORIZ_AXIS = (250, 204, 21)   # Cyan / Bright Yellow Horizontal Axis (#14ccfa in BGR)
COLOR_JOINTS = (147, 197, 253)      # Light Blue Arms & Legs (#fdc593 in BGR)
COLOR_MESH = (70, 70, 85)           # Very subtle mesh dots in DEBUG


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
        if not (0.0 <= x_f <= 1.0 and 0.0 <= y_f <= 1.0):
            return None
        vis = point.get("visibility")
        if vis is not None:
            vis_f = float(vis)
            if math.isnan(vis_f) or vis_f < 0.25:
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


def _draw_dashed_line(img: np.ndarray, pt1: Tuple[int, int], pt2: Tuple[int, int], color: Tuple[int, int, int], thickness: int = 1, gap: int = 6) -> None:
    """Draw dashed line between two points."""
    dist = math.hypot(pt2[0] - pt1[0], pt2[1] - pt1[1])
    if dist < 1.0:
        return
    dx = (pt2[0] - pt1[0]) / dist
    dy = (pt2[1] - pt1[1]) / dist
    curr = 0.0
    while curr < dist:
        p_start = (int(pt1[0] + curr * dx), int(pt1[1] + curr * dy))
        p_end = (int(pt1[0] + min(dist, curr + gap) * dx), int(pt1[1] + min(dist, curr + gap) * dy))
        cv2.line(img, p_start, p_end, color, thickness, cv2.LINE_AA)
        curr += gap * 2


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
        is_debug = (mode == "DEBUG")

        # 1. Pose Skeleton & Full Body Joints
        if pose_data and pose_data.get("pose_detected", False):
            landmarks = pose_data.get("landmarks", {})
            OverlayRenderer._render_pose_skeleton(canvas, landmarks, width, height, is_debug, pose_data)

        # 2. Face Geometry (Contours, Eyes, Nose, Mouth, Eyebrows, Chin)
        if face_data and face_data.get("face_detected", False):
            OverlayRenderer._render_face_geometry(canvas, face_data, width, height, is_debug)

        # 3. Reference Geometry (Horizontal Eye & Shoulder Axes, Vertical Head->Chin->Neck->Torso Axis)
        OverlayRenderer._render_reference_geometry(canvas, pose_data, face_data, width, height)

        # 4. Telemetry Overlay Badges (MINIMAL vs DEBUG)
        if is_debug:
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
            OverlayRenderer._render_minimal_badges(
                canvas,
                human_state=human_state,
                width=width,
                height=height,
            )

        return canvas

    @staticmethod
    def _render_pose_skeleton(
        canvas: np.ndarray,
        landmarks: Dict[str, Any],
        width: int,
        height: int,
        is_debug: bool = False,
        pose_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Draw complete body pose landmarks: shoulders, elbows, wrists, hips, knees, ankles."""
        pt_nose = _to_pixel(landmarks.get("nose"), width, height)
        pt_l_ear = _to_pixel(landmarks.get("left_ear"), width, height)
        pt_r_ear = _to_pixel(landmarks.get("right_ear"), width, height)
        pt_l_sh = _to_pixel(landmarks.get("left_shoulder"), width, height)
        pt_r_sh = _to_pixel(landmarks.get("right_shoulder"), width, height)
        pt_l_elb = _to_pixel(landmarks.get("left_elbow"), width, height)
        pt_r_elb = _to_pixel(landmarks.get("right_elbow"), width, height)
        pt_l_wri = _to_pixel(landmarks.get("left_wrist"), width, height)
        pt_r_wri = _to_pixel(landmarks.get("right_wrist"), width, height)
        pt_l_hip = _to_pixel(landmarks.get("left_hip"), width, height)
        pt_r_hip = _to_pixel(landmarks.get("right_hip"), width, height)
        pt_l_kne = _to_pixel(landmarks.get("left_knee"), width, height)
        pt_r_kne = _to_pixel(landmarks.get("right_knee"), width, height)
        pt_l_ank = _to_pixel(landmarks.get("left_ankle"), width, height)
        pt_r_ank = _to_pixel(landmarks.get("right_ankle"), width, height)

        # Head links
        _draw_connection(canvas, pt_l_ear, pt_nose, COLOR_ACCENT, 1)
        _draw_connection(canvas, pt_nose, pt_r_ear, COLOR_ACCENT, 1)

        # Upper Torso / Shoulder Axis
        _draw_connection(canvas, pt_l_sh, pt_r_sh, COLOR_ACCENT, 2)

        # Arms: Shoulders -> Elbows -> Wrists
        _draw_connection(canvas, pt_l_sh, pt_l_elb, COLOR_JOINTS, 2)
        _draw_connection(canvas, pt_l_elb, pt_l_wri, COLOR_JOINTS, 2)
        _draw_connection(canvas, pt_r_sh, pt_r_elb, COLOR_JOINTS, 2)
        _draw_connection(canvas, pt_r_elb, pt_r_wri, COLOR_JOINTS, 2)

        # Torso Sides
        _draw_connection(canvas, pt_l_sh, pt_l_hip, COLOR_ACCENT, 1)
        _draw_connection(canvas, pt_r_sh, pt_r_hip, COLOR_ACCENT, 1)

        # Hip Axis
        _draw_connection(canvas, pt_l_hip, pt_r_hip, COLOR_ACCENT, 1)

        # Legs: Hips -> Knees -> Ankles
        _draw_connection(canvas, pt_l_hip, pt_l_kne, COLOR_JOINTS, 1)
        _draw_connection(canvas, pt_l_kne, pt_l_ank, COLOR_JOINTS, 1)
        _draw_connection(canvas, pt_r_hip, pt_r_kne, COLOR_JOINTS, 1)
        _draw_connection(canvas, pt_r_kne, pt_r_ank, COLOR_JOINTS, 1)

        # Torso Center Line
        pt_sh_mid = None
        if pt_l_sh and pt_r_sh:
            pt_sh_mid = ((pt_l_sh[0] + pt_r_sh[0]) // 2, (pt_l_sh[1] + pt_r_sh[1]) // 2)

        pt_hip_mid = None
        if pt_l_hip and pt_r_hip:
            pt_hip_mid = ((pt_l_hip[0] + pt_r_hip[0]) // 2, (pt_l_hip[1] + pt_r_hip[1]) // 2)

        if pt_sh_mid and pt_hip_mid:
            _draw_connection(canvas, pt_sh_mid, pt_hip_mid, COLOR_TORSO, 2)
            _draw_node(canvas, pt_sh_mid, COLOR_TORSO, radius=4)
            _draw_node(canvas, pt_hip_mid, COLOR_TORSO, radius=4)

        # Primary landmark nodes
        for pt in (pt_nose, pt_l_ear, pt_r_ear, pt_l_sh, pt_r_sh, pt_l_elb, pt_r_elb, pt_l_wri, pt_r_wri,
                   pt_l_hip, pt_r_hip, pt_l_kne, pt_r_kne, pt_l_ank, pt_r_ank):
            if pt is not None:
                _draw_node(canvas, pt, COLOR_ACCENT, radius=3)

        # Dense skeleton nodes in DEBUG mode
        if is_debug and pose_data and "all_landmarks" in pose_data:
            for lm in pose_data["all_landmarks"]:
                p = _to_pixel(lm, width, height)
                if p is not None:
                    cv2.circle(canvas, p, 1, COLOR_WHITE, -1, cv2.LINE_AA)

    @staticmethod
    def _render_face_geometry(
        canvas: np.ndarray,
        face_data: Dict[str, Any],
        width: int,
        height: int,
        is_debug: bool = False,
    ) -> None:
        """Draw real alertness landmarks: eyes, mouth, nose, eyebrows, chin, jawline."""
        eyes = face_data.get("eye_landmarks", {})
        m_raw = face_data.get("mouth_landmarks", {})
        mouth = m_raw.get("mouth", m_raw) if isinstance(m_raw, dict) else {}
        head = face_data.get("head_reference", {})
        eyebrows = face_data.get("eyebrows", {})
        jawline = face_data.get("jawline", [])

        # 1. Left Eye
        l_eye = eyes.get("left_eye", {})
        l_outer = _to_pixel(l_eye.get("outer") or l_eye.get("p1"), width, height)
        l_inner = _to_pixel(l_eye.get("inner") or l_eye.get("p2"), width, height)
        l_top = _to_pixel(l_eye.get("top"), width, height)
        l_bottom = _to_pixel(l_eye.get("bottom"), width, height)
        l_top2 = _to_pixel(l_eye.get("top2"), width, height)
        l_bottom2 = _to_pixel(l_eye.get("bottom2"), width, height)

        if l_outer and l_inner and l_top and l_bottom:
            pts_l = [p for p in (l_outer, l_top2, l_top, l_inner, l_bottom, l_bottom2) if p is not None]
            for i in range(len(pts_l)):
                _draw_connection(canvas, pts_l[i], pts_l[(i + 1) % len(pts_l)], COLOR_GOOD, 1)
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
            _draw_connection(canvas, r_top, r_bottom, COLOR_WARNING, 1)
            for p in (r_outer, r_inner, r_top, r_bottom):
                _draw_node(canvas, p, COLOR_GOOD, radius=2)

        # 3. Eyebrows
        for eb_key in ("left_eyebrow", "right_eyebrow"):
            eb_pts = [_to_pixel(pt, width, height) for pt in eyebrows.get(eb_key, [])]
            valid_eb = [p for p in eb_pts if p is not None]
            for i in range(len(valid_eb) - 1):
                _draw_connection(canvas, valid_eb[i], valid_eb[i + 1], COLOR_MUTED, 1)

        # 4. Nose
        pt_nose_top = _to_pixel(head.get("nose_top"), width, height)
        pt_nose_tip = _to_pixel(head.get("nose_tip"), width, height)
        pt_nose_bot = _to_pixel(head.get("nose_bottom"), width, height)
        if pt_nose_top and pt_nose_tip:
            _draw_connection(canvas, pt_nose_top, pt_nose_tip, COLOR_ACCENT, 1)
        if pt_nose_tip and pt_nose_bot:
            _draw_connection(canvas, pt_nose_tip, pt_nose_bot, COLOR_ACCENT, 1)

        # 5. Mouth
        m_top = _to_pixel(mouth.get("top") or mouth.get("p1"), width, height)
        m_bottom = _to_pixel(mouth.get("bottom") or mouth.get("p2"), width, height)
        m_left = _to_pixel(mouth.get("left"), width, height)
        m_right = _to_pixel(mouth.get("right"), width, height)

        if m_top and m_bottom and m_left and m_right:
            _draw_connection(canvas, m_left, m_top, COLOR_ACCENT, 1)
            _draw_connection(canvas, m_top, m_right, COLOR_ACCENT, 1)
            _draw_connection(canvas, m_right, m_bottom, COLOR_ACCENT, 1)
            _draw_connection(canvas, m_bottom, m_left, COLOR_ACCENT, 1)
            _draw_connection(canvas, m_top, m_bottom, COLOR_WARNING, 1)
            for p in (m_left, m_right, m_top, m_bottom):
                _draw_node(canvas, p, COLOR_ACCENT, radius=2)

        # 6. Jawline / Chin
        pt_chin = _to_pixel(head.get("chin"), width, height)
        if pt_chin:
            _draw_node(canvas, pt_chin, COLOR_ACCENT, radius=3)

        if jawline:
            jaw_px = [_to_pixel(pt, width, height) for pt in jawline]
            valid_jaw = [p for p in jaw_px if p is not None]
            for i in range(len(valid_jaw) - 1):
                _draw_connection(canvas, valid_jaw[i], valid_jaw[i + 1], COLOR_MUTED, 1)

        # 7. Dense Face Mesh (ONLY in DEBUG mode, never in MINIMAL mode)
        if is_debug and "all_landmarks" in face_data:
            all_lms = face_data["all_landmarks"]
            for lm in all_lms:
                p = _to_pixel(lm, width, height)
                if p is not None:
                    cv2.circle(canvas, p, 1, COLOR_MESH, -1, cv2.LINE_AA)

    @staticmethod
    def _render_reference_geometry(
        canvas: np.ndarray,
        pose_data: Optional[Dict[str, Any]],
        face_data: Optional[Dict[str, Any]],
        width: int,
        height: int,
    ) -> None:
        """Render explicit Horizontal and Vertical Reference Axes.

        HORIZONTAL:
          - Eye line connecting left and right eye centers
          - Shoulder line connecting left and right shoulders

        VERTICAL:
          - Head center -> chin -> neck center -> torso center
        """
        # --- Horizontal Eye Axis ---
        pt_l_eye_center = None
        pt_r_eye_center = None
        if face_data and face_data.get("face_detected", False):
            eyes = face_data.get("eye_landmarks", {})
            l_e = eyes.get("left_eye", {})
            r_e = eyes.get("right_eye", {})
            p_lo = _to_pixel(l_e.get("outer"), width, height)
            p_li = _to_pixel(l_e.get("inner"), width, height)
            p_ro = _to_pixel(r_e.get("outer"), width, height)
            p_ri = _to_pixel(r_e.get("inner"), width, height)
            if p_lo and p_li:
                pt_l_eye_center = ((p_lo[0] + p_li[0]) // 2, (p_lo[1] + p_li[1]) // 2)
            if p_ro and p_ri:
                pt_r_eye_center = ((p_ro[0] + p_ri[0]) // 2, (p_ro[1] + p_ri[1]) // 2)

            if pt_l_eye_center and pt_r_eye_center:
                # Horizontal eye line
                _draw_connection(canvas, pt_l_eye_center, pt_r_eye_center, COLOR_HORIZ_AXIS, 1)
                _draw_node(canvas, pt_l_eye_center, COLOR_HORIZ_AXIS, radius=2)
                _draw_node(canvas, pt_r_eye_center, COLOR_HORIZ_AXIS, radius=2)

        # --- Shoulder Axis & Midpoints ---
        pt_sh_mid = None
        pt_l_sh = None
        pt_r_sh = None
        pt_hip_mid = None
        if pose_data and pose_data.get("pose_detected", False):
            landmarks = pose_data.get("landmarks", {})
            pt_l_sh = _to_pixel(landmarks.get("left_shoulder"), width, height)
            pt_r_sh = _to_pixel(landmarks.get("right_shoulder"), width, height)
            pt_l_hip = _to_pixel(landmarks.get("left_hip"), width, height)
            pt_r_hip = _to_pixel(landmarks.get("right_hip"), width, height)

            if pt_l_sh and pt_r_sh:
                pt_sh_mid = ((pt_l_sh[0] + pt_r_sh[0]) // 2, (pt_l_sh[1] + pt_r_sh[1]) // 2)
                # Draw extended horizontal shoulder axis
                _draw_connection(canvas, pt_l_sh, pt_r_sh, COLOR_HORIZ_AXIS, 2)

            if pt_l_hip and pt_r_hip:
                pt_hip_mid = ((pt_l_hip[0] + pt_r_hip[0]) // 2, (pt_l_hip[1] + pt_r_hip[1]) // 2)

        # --- Vertical Axis: Head Center -> Chin -> Neck Center -> Torso Center ---
        pt_head_center = None
        pt_chin = None
        if face_data and face_data.get("face_detected", False):
            head = face_data.get("head_reference", {})
            p_forehead = _to_pixel(head.get("forehead"), width, height)
            pt_chin = _to_pixel(head.get("chin"), width, height)
            if p_forehead and pt_chin:
                pt_head_center = ((p_forehead[0] + pt_chin[0]) // 2, (p_forehead[1] + pt_chin[1]) // 2)
            elif pt_l_eye_center and pt_r_eye_center:
                pt_head_center = ((pt_l_eye_center[0] + pt_r_eye_center[0]) // 2, (pt_l_eye_center[1] + pt_r_eye_center[1]) // 2)

        # Neck center: midpoint between chin and shoulder midpoint
        pt_neck_center = None
        if pt_chin and pt_sh_mid:
            pt_neck_center = ((pt_chin[0] + pt_sh_mid[0]) // 2, (pt_chin[1] + pt_sh_mid[1]) // 2)
        elif pt_sh_mid:
            pt_neck_center = (pt_sh_mid[0], max(0, pt_sh_mid[1] - 25))

        # Torso center: midpoint between shoulder midpoint and hip midpoint
        pt_torso_center = None
        if pt_sh_mid and pt_hip_mid:
            pt_torso_center = ((pt_sh_mid[0] + pt_hip_mid[0]) // 2, (pt_sh_mid[1] + pt_hip_mid[1]) // 2)
        elif pt_sh_mid:
            pt_torso_center = (pt_sh_mid[0], min(height - 1, pt_sh_mid[1] + 50))

        # Draw Vertical Axis chain
        vert_chain = [p for p in (pt_head_center, pt_chin, pt_neck_center, pt_torso_center) if p is not None]
        if len(vert_chain) >= 2:
            for i in range(len(vert_chain) - 1):
                _draw_dashed_line(canvas, vert_chain[i], vert_chain[i + 1], COLOR_VERT_AXIS, thickness=2, gap=5)
            for p in vert_chain:
                _draw_node(canvas, p, COLOR_VERT_AXIS, radius=3)

    @staticmethod
    def _render_minimal_badges(canvas: np.ndarray, human_state: Optional[Any], width: int, height: int) -> None:
        """Draw clean, unobtrusive telemetry badges in corners."""
        if human_state is None:
            return

        posture = getattr(human_state, "posture_status", "NOT_CALIBRATED") or "NOT_CALIBRATED"
        alertness = getattr(human_state, "alertness_status", "NOT_CALIBRATED") or "NOT_CALIBRATED"
        eye_state = getattr(human_state, "eye_state", "UNKNOWN") or "UNKNOWN"
        closure_sec = getattr(human_state, "eye_closure_duration", 0.0) or 0.0
        blinks = getattr(human_state, "blink_count", 0) or 0
        activity = getattr(human_state, "activity_state", "UNKNOWN") or "UNKNOWN"

        p_color = COLOR_GOOD if posture == "GOOD" else COLOR_WARNING if posture in ("SLOUCHING", "FORWARD_LEAN", "LEFT_LEAN", "RIGHT_LEAN") else COLOR_MUTED
        a_color = COLOR_GOOD if alertness == "ALERT" else COLOR_HIGH if alertness == "POSSIBLE_DROWSINESS" else COLOR_MUTED

        box_w = 230
        box_h = 74
        x1 = width - box_w - 12
        y1 = 12

        sub_img = canvas[y1:y1 + box_h, x1:x1 + box_w]
        dark_rect = np.zeros(sub_img.shape, dtype=np.uint8)
        cv2.addWeighted(sub_img, 0.35, dark_rect, 0.65, 0, sub_img)
        cv2.rectangle(canvas, (x1, y1), (x1 + box_w, y1 + box_h), (50, 65, 85), 1)

        cv2.putText(canvas, f"ACTIVITY: {activity}", (x1 + 8, y1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, COLOR_ACCENT, 1, cv2.LINE_AA)
        cv2.putText(canvas, f"POSTURE: {posture}", (x1 + 8, y1 + 36), cv2.FONT_HERSHEY_SIMPLEX, 0.42, p_color, 1, cv2.LINE_AA)

        eye_text = f"ALERTNESS: {alertness} | {eye_state}"
        if closure_sec > 0.5:
            eye_text += f" ({closure_sec:.1f}s)"
        cv2.putText(canvas, eye_text, (x1 + 8, y1 + 54), cv2.FONT_HERSHEY_SIMPLEX, 0.38, a_color, 1, cv2.LINE_AA)
        cv2.putText(canvas, f"Blinks: {blinks}", (x1 + 8, y1 + 68), cv2.FONT_HERSHEY_SIMPLEX, 0.35, COLOR_MUTED, 1, cv2.LINE_AA)

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
        """Render detailed derived metrics overlay including exact calculated degrees and angles."""
        p_status = getattr(human_state, "posture_status", "UNKNOWN") or "UNKNOWN"
        p_score = getattr(human_state, "posture_score", None)
        a_status = getattr(human_state, "alertness_status", "UNKNOWN") or "UNKNOWN"
        a_score = getattr(human_state, "alertness_score", None)
        risk_lvl = getattr(human_state, "risk_level", "UNKNOWN") or "UNKNOWN"
        risk_sc = getattr(human_state, "risk_score", None)
        closure = getattr(human_state, "eye_closure_duration", 0.0) or 0.0
        blinks = getattr(human_state, "blink_count", 0) or 0
        activity = getattr(human_state, "activity_state", "UNKNOWN") or "UNKNOWN"
        base_src = getattr(human_state, "baseline_source", "BUILT_IN") or "BUILT_IN"

        ear_val = getattr(face_geom, "combined_ear", None)
        mor_val = getattr(face_geom, "mouth_ratio", None)

        pitch_deg = round(float(face_geom.head_pitch_ratio * 90.0), 1) if (face_geom and getattr(face_geom, "head_pitch_ratio", None) is not None) else 0.0
        yaw_deg = round(float(getattr(face_geom, "head_yaw_ratio", 0.0) * 90.0), 1) if face_geom else 0.0
        tilt_deg = round(float(getattr(posture_geom, "shoulder_tilt", 0.0) * 45.0), 1) if posture_geom else 0.0
        neck_deg = round(float(getattr(posture_geom, "slouch_proxy", 0.0) * 50.0), 1) if posture_geom else 0.0

        ear_str = f"{ear_val:.3f}" if ear_val is not None else "-"
        mor_str = f"{mor_val:.3f}" if mor_val is not None else "-"
        closure_str = f"{closure:.2f}s" if isinstance(closure, (int, float)) else "-"
        p_sc_str = f"{p_score:.1f}" if isinstance(p_score, (int, float)) else "-"
        a_sc_str = f"{a_score:.1f}" if isinstance(a_score, (int, float)) else "-"
        r_sc_str = f"{risk_sc:.1f}" if isinstance(risk_sc, (int, float)) else "-"

        closed_thresh = getattr(alertness_baseline, "closed_eye_threshold", None)
        thresh_str = f"{closed_thresh:.3f}" if closed_thresh is not None else "-"
        eye_st = getattr(human_state, "eye_state", "UNKNOWN") or "UNKNOWN"
        blink_cand = getattr(human_state, "is_blink_candidate", False)
        blink_rate_val = getattr(human_state, "blink_rate", None)
        br_str = f"{blink_rate_val}/min" if blink_rate_val is not None else "-"

        lines = [
            "DEBUG GEOMETRY & TELEMETRY (LIVE)",
            f"Baseline: {base_src} | Activity: {activity}",
            f"Posture: {p_status} (Score: {p_sc_str})",
            f"Eyes: {eye_st} | EAR: {ear_str} (Thresh: {thresh_str})",
            f"Closure: {closure_str} | BlinkCand: {blink_cand} | Blinks: {blinks} ({br_str})",
            f"Alertness: {a_status} (Score: {a_sc_str}) | MOR: {mor_str}",
            f"Angles: Pitch: {pitch_deg}* | Yaw: {yaw_deg}* | Tilt: {tilt_deg}*",
            f"Neck Inclination: {neck_deg}* | Torso: Active",
            f"Risk: {risk_lvl} ({r_sc_str})",
        ]

        box_w = 300
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
            cv2.putText(canvas, text, (x1 + 10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)
            y_offset += 20
