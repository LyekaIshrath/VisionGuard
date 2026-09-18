from __future__ import annotations

import os
from typing import Optional, Any, Dict
import cv2
import numpy as np

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
except ImportError:
    mp = None
    mp_python = None
    vision = None

from app.human_state.models import HumanState


def _get_model_path(model_filename: str) -> Optional[str]:
    """Find local task model file in backend/models."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.abspath(os.path.join(current_dir, "..", "..", "models", model_filename)),
        os.path.abspath(os.path.join(current_dir, "..", "models", model_filename)),
        os.path.abspath(os.path.join("backend", "models", model_filename)),
        os.path.abspath(os.path.join("models", model_filename)),
    ]
    for p in candidates:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return None


class MediaPipePose:
    """MediaPipe pose landmark detection using Tasks API (PoseLandmarker).

    Returns pose detection status and relevant landmark coordinates.
    Provides key landmarks:
    - nose
    - left/right ear
    - left/right shoulder
    - left/right hip
    """

    def __init__(self,
                 min_detection_confidence: float = 0.5,
                 min_tracking_confidence: float = 0.5):
        self._landmarker: Any = None
        self._last_result: Any = None
        self._last_confidence: float = 0.0

        if mp is not None and vision is not None:
            model_path = _get_model_path("pose_landmarker_lite.task")
            if model_path:
                try:
                    options = vision.PoseLandmarkerOptions(
                        base_options=mp_python.BaseOptions(model_asset_path=model_path),
                        min_pose_detection_confidence=min_detection_confidence,
                        min_tracking_confidence=min_tracking_confidence,
                    )
                    self._landmarker = vision.PoseLandmarker.create_from_options(options)
                except Exception:
                    self._landmarker = None

    def detect(self, image: Any) -> dict:
        """Detect pose in an image.

        Returns dict with pose_detected and landmark coordinates.
        The image should be RGB format, ready for MediaPipe processing.
        """
        if self._landmarker is None or image is None:
            return {
                "pose_detected": False,
                "landmarks": {},
                "confidence": 0.0,
            }

        try:
            # Ensure image is in RGB format uint8
            if hasattr(image, 'shape') and len(image.shape) == 3 and image.shape[2] == 3:
                rgb_image = np.ascontiguousarray(image, dtype=np.uint8)
            else:
                return {
                    "pose_detected": False,
                    "landmarks": {},
                    "confidence": 0.0,
                }

            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
            self._last_result = self._landmarker.detect(mp_image)

            if self._last_result and self._last_result.pose_landmarks and len(self._last_result.pose_landmarks) > 0:
                lms = self._last_result.pose_landmarks[0]

                # Extract key landmarks
                key_points = {}
                key_idx = {
                    'nose': 0,
                    'left_ear': 7,
                    'right_ear': 8,
                    'left_shoulder': 11,
                    'right_shoulder': 12,
                    'left_hip': 23,
                    'right_hip': 24,
                }

                visibilities = []
                for name, idx in key_idx.items():
                    if idx < len(lms):
                        lm = lms[idx]
                        vis = getattr(lm, 'visibility', 1.0)
                        if vis is None:
                            vis = 1.0
                        pres = getattr(lm, 'presence', 1.0)
                        if pres is None:
                            pres = 1.0
                        key_points[name] = {
                            'x': float(lm.x),
                            'y': float(lm.y),
                            'z': float(lm.z) if hasattr(lm, 'z') else 0.0,
                            'visibility': float(vis),
                            'presence': float(pres),
                        }
                        visibilities.append(float(vis))
                    else:
                        key_points[name] = None

                self._last_confidence = (
                    sum(visibilities) / len(visibilities) if visibilities else 1.0
                )

                return {
                    "pose_detected": True,
                    "landmarks": key_points,
                    "confidence": round(self._last_confidence, 4),
                }
            else:
                return {
                    "pose_detected": False,
                    "landmarks": {},
                    "confidence": 0.0,
                }
        except Exception:
            return {
                "pose_detected": False,
                "landmarks": {},
                "confidence": 0.0,
            }

    def release(self) -> None:
        """Release MediaPipe resources."""
        try:
            if self._landmarker:
                self._landmarker.close()
                self._landmarker = None
        except Exception:
            pass


class MediaPipeFace:
    """MediaPipe face landmark detection using Tasks API (FaceLandmarker).

    Returns face detection status and relevant landmark coordinates.
    Provides eye, mouth, and head-reference landmarks.
    """

    def __init__(self,
                 min_detection_confidence: float = 0.5,
                 min_tracking_confidence: float = 0.5):
        self._landmarker: Any = None
        self._last_result: Any = None
        self._last_confidence: float = 0.0

        if mp is not None and vision is not None:
            model_path = _get_model_path("face_landmarker.task")
            if model_path:
                try:
                    options = vision.FaceLandmarkerOptions(
                        base_options=mp_python.BaseOptions(model_asset_path=model_path),
                        min_face_detection_confidence=min_detection_confidence,
                        min_tracking_confidence=min_tracking_confidence,
                        num_faces=1,
                    )
                    self._landmarker = vision.FaceLandmarker.create_from_options(options)
                except Exception:
                    self._landmarker = None

    def detect(self, image: Any) -> dict:
        """Detect face landmarks in an image."""
        if self._landmarker is None or image is None:
            return {
                "face_detected": False,
                "eye_landmarks": {},
                "mouth_landmarks": {},
                "head_reference": {},
                "confidence": 0.0,
            }

        try:
            if hasattr(image, 'shape') and len(image.shape) == 3 and image.shape[2] == 3:
                rgb_image = np.ascontiguousarray(image, dtype=np.uint8)
            else:
                return {
                    "face_detected": False,
                    "eye_landmarks": {},
                    "mouth_landmarks": {},
                    "head_reference": {},
                    "confidence": 0.0,
                }

            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
            self._last_result = self._landmarker.detect(mp_image)

            if self._last_result and self._last_result.face_landmarks and len(self._last_result.face_landmarks) > 0:
                lms = self._last_result.face_landmarks[0]
                self._last_confidence = 1.0

                def _pt(idx: int):
                    if idx < len(lms):
                        lm = lms[idx]
                        return {
                            "x": float(lm.x),
                            "y": float(lm.y),
                            "z": float(getattr(lm, "z", 0.0)),
                        }
                    return None

                eye_landmarks = {
                    "left_eye": {
                        "p1": _pt(33),
                        "p2": _pt(133),
                        "outer": _pt(33),
                        "inner": _pt(133),
                        "top": _pt(159),
                        "bottom": _pt(145),
                        "top2": _pt(158),
                        "bottom2": _pt(153),
                    },
                    "right_eye": {
                        "p1": _pt(263),
                        "p2": _pt(249),
                        "outer": _pt(263),
                        "inner": _pt(362),
                        "top": _pt(386),
                        "bottom": _pt(374),
                        "top2": _pt(387),
                        "bottom2": _pt(373),
                    },
                }

                mouth_landmarks = {
                    "mouth": {
                        "p1": _pt(13),
                        "p2": _pt(14),
                        "p3": _pt(15),
                        "top": _pt(13),
                        "bottom": _pt(14),
                        "left": _pt(61),
                        "right": _pt(291),
                    }
                }

                head_ref = {
                    "forehead": _pt(10),
                    "nose_tip": _pt(1),
                    "chin": _pt(152),
                }

                return {
                    "face_detected": True,
                    "eye_landmarks": eye_landmarks,
                    "mouth_landmarks": mouth_landmarks,
                    "head_reference": head_ref,
                    "confidence": self._last_confidence,
                }
            else:
                return {
                    "face_detected": False,
                    "eye_landmarks": {},
                    "mouth_landmarks": {},
                    "head_reference": {},
                    "confidence": 0.0,
                }
        except Exception:
            return {
                "face_detected": False,
                "eye_landmarks": {},
                "mouth_landmarks": {},
                "head_reference": {},
                "confidence": 0.0,
            }

    def release(self) -> None:
        """Release MediaPipe resources."""
        try:
            if self._landmarker:
                self._landmarker.close()
                self._landmarker = None
        except Exception:
            pass

