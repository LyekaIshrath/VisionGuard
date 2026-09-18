from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import cv2
import numpy as np

from app.camera.webcam_source import WebcamSource
from app.perception.mediapipe_pose import MediaPipePose, MediaPipeFace
from app.human_state.models import HumanState
from app.posture.geometry import extract_body_geometry, BodyGeometry
from app.posture.calibration import PostureCalibrationService, CalibrationState
from app.posture.analyzer import PostureAnalyzer, PostureStatus
from app.alertness.geometry import extract_face_geometry, FaceGeometry
from app.alertness.calibration import AlertnessCalibrationService, CalibrationState as AlertnessCalibrationState
from app.alertness.analyzer import AlertnessAnalyzer, AlertnessStatus
from app.intelligence.risk_engine import RiskEngine
from app.intelligence.risk_models import RiskLevel
from app.alerts.engine import InterventionEngine
from app.sessions.service import session_service
from app.perception.overlay import OverlayRenderer


class PerceptionEngine:
    """Authoritative perception pipeline: MediaPipe Pose + Face -> HumanState.

    Integrates:
    - MediaPipe Pose & Face detection
    - Normalized body geometry extraction & Posture intelligence (Mission 03)
    - Facial geometry extraction & Alertness/Drowsiness intelligence (Mission 04)
    - Single authoritative HumanState generator
    """

    def __init__(self, camera_index: int = 0):
        self._pose = MediaPipePose()
        self._face = MediaPipeFace()
        self._calibration_service = PostureCalibrationService()
        self._posture_analyzer = PostureAnalyzer()
        self._alertness_calibration_service = AlertnessCalibrationService()
        self._alertness_analyzer = AlertnessAnalyzer()
        self._risk_engine = RiskEngine()
        self._intervention_engine = InterventionEngine()
        self._intervention_engine.add_event_listener(session_service.record_risk_event)
        self._latest_state = HumanState(track_id="visionguard-001")
        self._overlay_renderer = OverlayRenderer()
        self._latest_raw_frame: Optional[np.ndarray] = None
        self._latest_pose_result: Optional[Dict[str, Any]] = None
        self._latest_face_result: Optional[Dict[str, Any]] = None
        self._latest_body_geom: Optional[BodyGeometry] = None
        self._latest_face_geom: Optional[FaceGeometry] = None
        self._latest_posture_res: Optional[Any] = None
        self._latest_alertness_res: Optional[Any] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._worker_running: bool = False
        self._worker_frames_processed: int = 0
        self._last_processed_frame_id: int = -1
        self._lock = threading.Lock()

    @property
    def calibration_service(self) -> PostureCalibrationService:
        return self._calibration_service

    @property
    def posture_analyzer(self) -> PostureAnalyzer:
        return self._posture_analyzer

    @property
    def alertness_calibration_service(self) -> AlertnessCalibrationService:
        return self._alertness_calibration_service

    @property
    def alertness_analyzer(self) -> AlertnessAnalyzer:
        return self._alertness_analyzer

    @property
    def risk_engine(self) -> RiskEngine:
        return self._risk_engine

    @property
    def intervention_engine(self) -> InterventionEngine:
        return self._intervention_engine

    def start_worker(self, manager: Any) -> None:
        """Start dedicated background perception worker thread consuming newest frames."""
        with self._lock:
            if self._worker_running:
                return
            self._worker_running = True
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                args=(manager,),
                daemon=True,
                name="PerceptionWorkerThread",
            )
            self._worker_thread.start()

    def stop_worker(self) -> None:
        """Stop dedicated background perception worker thread."""
        self._worker_running = False
        if self._worker_thread is not None:
            try:
                self._worker_thread.join(timeout=2.0)
            except Exception:
                pass
            self._worker_thread = None

    def _worker_loop(self, manager: Any) -> None:
        """Worker loop continuously consuming newest raw frame without blocking capture."""
        import time
        while self._worker_running:
            try:
                if hasattr(manager, "get_latest_raw_frame"):
                    frame_id, raw_frame = manager.get_latest_raw_frame()
                    if raw_frame is not None and frame_id > self._last_processed_frame_id:
                        self._last_processed_frame_id = frame_id
                        self.process_frame(raw_frame)
                        self._worker_frames_processed += 1
                time.sleep(0.005)
            except Exception:
                time.sleep(0.02)

    def reset_session(self) -> None:
        """Reset transient temporal accumulators on monitoring start."""
        with self._lock:
            self._risk_engine.reset_session()
            self._intervention_engine.reset_session()
            self._latest_raw_frame = None
            self._latest_pose_result = None
            self._latest_face_result = None
            self._latest_body_geom = None
            self._latest_face_geom = None
            self._latest_posture_res = None
            self._latest_alertness_res = None

    def stop_session(self) -> None:
        """Stop accumulation and pause timers on monitoring stop."""
        with self._lock:
            self._risk_engine.stop_session()
            self._latest_raw_frame = None
            self._latest_pose_result = None
            self._latest_face_result = None
            self._latest_body_geom = None
            self._latest_face_geom = None
            self._latest_posture_res = None
            self._latest_alertness_res = None

    def process_frame(self, frame_input: Optional[Union[bytes, np.ndarray]]) -> HumanState:
        """Process a single frame buffer into an updated HumanState."""
        with self._lock:
            if frame_input is None:
                state = HumanState(
                    timestamp=datetime.now(timezone.utc),
                    track_id="visionguard-001",
                    person_detected=False,
                    face_detected=False,
                    pose_detected=False,
                    posture_status=(
                        PostureStatus.UNKNOWN.value
                        if self._calibration_service.is_calibrated
                        else PostureStatus.NOT_CALIBRATED.value
                    ),
                    posture_score=None,
                    alertness_status=(
                        AlertnessStatus.UNKNOWN.value
                        if self._alertness_calibration_service.is_calibrated
                        else None
                    ),
                    alertness_score=None,
                    eye_state="UNKNOWN" if self._alertness_calibration_service.is_calibrated else None,
                    confidence=0.0,
                )
                self._latest_state = state
                return state

            if isinstance(frame_input, np.ndarray):
                frame = frame_input
            elif isinstance(frame_input, (bytes, bytearray)):
                try:
                    nparr = np.frombuffer(frame_input, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                except Exception:
                    frame = None
            else:
                frame = None

            if frame is None:
                state = HumanState(
                    timestamp=datetime.now(timezone.utc),
                    track_id="visionguard-001",
                    person_detected=False,
                    face_detected=False,
                    pose_detected=False,
                    posture_status=(
                        PostureStatus.UNKNOWN.value
                        if self._calibration_service.is_calibrated
                        else PostureStatus.NOT_CALIBRATED.value
                    ),
                    posture_score=None,
                    alertness_status=(
                        AlertnessStatus.UNKNOWN.value
                        if self._alertness_calibration_service.is_calibrated
                        else None
                    ),
                    alertness_score=None,
                    eye_state="UNKNOWN" if self._alertness_calibration_service.is_calibrated else None,
                    confidence=0.0,
                )
                self._latest_state = state
                return state

            self._latest_raw_frame = frame
            # Convert BGR to RGB for MediaPipe
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            except Exception:
                rgb = frame

            # Run detectors
            pose_result = self._pose.detect(rgb)
            face_result = self._face.detect(rgb)

            self._latest_pose_result = pose_result
            self._latest_face_result = face_result
            pose_detected = pose_result.get("pose_detected", False)
            face_detected = face_result.get("face_detected", False)
            person_detected = pose_detected or face_detected

            # Confidence aggregation
            pose_conf = pose_result.get("confidence", 0.0)
            face_conf = face_result.get("confidence", 0.0)
            overall_conf = max(pose_conf or 0.0, face_conf or 0.0)

            # --- Mission 03: Posture Geometry Extraction & Analysis ---
            body_geom: Optional[BodyGeometry] = None
            if pose_detected and "landmarks" in pose_result:
                body_geom = extract_body_geometry(pose_result["landmarks"])

            self._latest_body_geom = body_geom
            # Posture Calibration lifecycle
            if self._calibration_service.state == CalibrationState.COLLECTING:
                new_state = self._calibration_service.add_sample(body_geom)
                if new_state == CalibrationState.COMPLETED:
                    self._posture_analyzer.set_baseline(self._calibration_service.baseline)

            # Posture analysis
            if self._calibration_service.is_calibrated:
                if self._posture_analyzer._baseline != self._calibration_service.baseline:
                    self._posture_analyzer.set_baseline(self._calibration_service.baseline)

                posture_res = self._posture_analyzer.analyze(body_geom)
                posture_status = posture_res.stable_status.value
                posture_score = posture_res.smoothed_score
                posture_conf = posture_res.confidence
                self._latest_posture_res = posture_res
            else:
                self._latest_posture_res = None
                posture_status = PostureStatus.NOT_CALIBRATED.value
                posture_score = None
                posture_conf = body_geom.confidence if body_geom else (pose_conf if pose_detected else None)

            # --- Mission 04: Alertness Geometry Extraction & Analysis ---
            face_geom: Optional[FaceGeometry] = None
            if face_detected:
                face_geom = extract_face_geometry(face_result)

            self._latest_face_geom = face_geom
            # Alertness Calibration lifecycle
            if self._alertness_calibration_service.state == AlertnessCalibrationState.COLLECTING:
                new_alert_state = self._alertness_calibration_service.add_sample(face_geom)
                if new_alert_state == AlertnessCalibrationState.COMPLETED:
                    self._alertness_analyzer.set_baseline(self._alertness_calibration_service.baseline)

            # Alertness analysis
            if self._alertness_calibration_service.is_calibrated:
                if self._alertness_analyzer._baseline != self._alertness_calibration_service.baseline:
                    self._alertness_analyzer.set_baseline(self._alertness_calibration_service.baseline)

                alert_res = self._alertness_analyzer.analyze(face_geom)
                alertness_status = alert_res.status.value
                alertness_score = alert_res.score
                eye_state = alert_res.eye_state
                eye_closure_dur = alert_res.eye_closure_duration
                blink_rate = alert_res.blink_rate
                yawn_score = alert_res.yawn_score
                head_pitch = alert_res.head_pitch
                alert_conf = alert_res.confidence
                self._latest_alertness_res = alert_res
            else:
                self._latest_alertness_res = None
                alertness_status = None
                alertness_score = None
                eye_state = None
                eye_closure_dur = None
                blink_rate = None
                yawn_score = None
                head_pitch = face_geom.head_pitch_ratio if face_geom else None
                alert_conf = face_geom.confidence if face_geom else 0.0

            final_conf = max(posture_conf or 0.0, alert_conf or 0.0, overall_conf)

            state = HumanState(
                timestamp=datetime.now(timezone.utc),
                track_id="visionguard-001",
                person_detected=person_detected,
                face_detected=face_detected,
                pose_detected=pose_detected,
                posture_status=posture_status,
                posture_score=posture_score,
                alertness_status=alertness_status,
                alertness_score=alertness_score,
                eye_state=eye_state,
                eye_closure_duration=eye_closure_dur,
                blink_rate=blink_rate,
                yawn_score=yawn_score,
                head_pitch=head_pitch,
                confidence=round(final_conf, 2),
            )

            # --- Mission 05: Temporal Risk & Intervention Engine ---
            risk_state = self._risk_engine.evaluate(state)
            if not self._calibration_service.is_calibrated and not self._alertness_calibration_service.is_calibrated:
                # Uncalibrated baseline
                state.risk_level = None
                state.risk_score = None
            elif risk_state.level == RiskLevel.UNKNOWN:
                state.risk_level = RiskLevel.UNKNOWN.value
                state.risk_score = None
            else:
                state.risk_level = risk_state.level.value
                state.risk_score = risk_state.score

            self._intervention_engine.evaluate(risk_state)
            self._latest_state = state
            session_service.on_frame_processed(state)
            return state

    def get_annotated_frame_bytes(self, mode: str = "MINIMAL", current_frame: Optional[np.ndarray] = None) -> Optional[bytes]:
        """Render landmark skeleton and telemetry overlay onto latest frame.

        Does NOT open a second camera or run inference twice.
        Does NOT persist frames to disk or write landmarks to database.
        Returns transient JPEG bytes in-memory.
        """
        with self._lock:
            target_frame = current_frame if current_frame is not None else self._latest_raw_frame
            if target_frame is None:
                return None

            normalized_mode = mode.upper() if mode else "MINIMAL"
            if normalized_mode == "OFF":
                success, buf = cv2.imencode(".jpg", target_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                return buf.tobytes() if success else None

            annotated = self._overlay_renderer.render(
                frame=target_frame,
                mode=normalized_mode,
                pose_data=self._latest_pose_result,
                face_data=self._latest_face_result,
                human_state=self._latest_state,
                posture_geom=self._latest_body_geom,
                face_geom=self._latest_face_geom,
                posture_res=self._latest_posture_res,
                alertness_res=self._latest_alertness_res,
                posture_baseline=self._posture_analyzer._baseline,
                alertness_baseline=self._alertness_analyzer._baseline,
            )
            success, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
            return buf.tobytes() if success else None

    def analyze(self, source: WebcamSource) -> Optional[HumanState]:
        """Preserve existing method: analyze latest frame from WebcamSource."""
        frame_bytes = source.read()
        return self.process_frame(frame_bytes)

    def get_latest_state(self) -> HumanState:
        """Return the most recently computed HumanState."""
        with self._lock:
            return self._latest_state

    def reset_posture(self) -> None:
        """Reset posture calibration and posture analyzer state."""
        with self._lock:
            self._calibration_service.reset_calibration()
            self._posture_analyzer.set_baseline(None)
            if self._latest_state is not None:
                self._latest_state.posture_status = PostureStatus.NOT_CALIBRATED.value
                self._latest_state.posture_score = None

    def reset_alertness(self) -> None:
        """Reset alertness calibration and alertness analyzer state."""
        with self._lock:
            self._alertness_calibration_service.reset_calibration()
            self._alertness_analyzer.set_baseline(None)
            if self._latest_state is not None:
                self._latest_state.alertness_status = None
                self._latest_state.alertness_score = None
                self._latest_state.eye_state = None
                self._latest_state.eye_closure_duration = None
                self._latest_state.blink_rate = None
                self._latest_state.yawn_score = None
                self._latest_state.head_pitch = None

    def release(self) -> None:
        """Release MediaPipe resources."""
        try:
            self._pose.release()
        except Exception:
            pass
        try:
            self._face.release()
        except Exception:
            pass


# Module-level singleton
_perception_engine: Optional[PerceptionEngine] = None
_engine_lock = threading.Lock()


def get_perception_engine() -> PerceptionEngine:
    """Get or create the module-level PerceptionEngine instance."""
    global _perception_engine
    with _engine_lock:
        if _perception_engine is None:
            _perception_engine = PerceptionEngine()
        return _perception_engine
