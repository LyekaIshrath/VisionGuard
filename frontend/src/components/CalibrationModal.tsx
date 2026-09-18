import React from "react";
import { CalibrationStatus, AlertnessCalibrationStatus } from "../types";

interface CalibrationModalProps {
  type: "posture" | "alertness";
  isOpen: boolean;
  onClose: () => void;
  status: CalibrationStatus | AlertnessCalibrationStatus;
  isActionInProgress: boolean;
  onStart: () => void;
  onReset: () => void;
}

export const CalibrationModal: React.FC<CalibrationModalProps> = ({
  type,
  isOpen,
  onClose,
  status,
  isActionInProgress,
  onStart,
  onReset,
}) => {
  if (!isOpen) return null;

  const isPosture = type === "posture";
  const title = isPosture ? "Personal Posture Calibration" : "Personal Alertness Calibration";
  const isCollecting = status.state === "COLLECTING";
  const isCompleted = status.state === "COMPLETED";
  const isFailed = status.state === "FAILED";

  const progressPercent = Math.round((status.progress || 0) * 100);

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-group">
            <h3 className="modal-title" id="modal-title">{title}</h3>
            <span className="modal-subtitle">Individual Biomechanical Baseline Acquisition</span>
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close dialog">
            &times;
          </button>
        </div>

        <div className="modal-body">
          {isPosture ? (
            <div className="calibration-steps">
              <div className="step-item">
                <span className="step-number">1</span>
                <div className="step-content">
                  <strong>Sit naturally upright</strong>
                  <p>Assume your preferred comfortable working posture facing your monitor.</p>
                </div>
              </div>
              <div className="step-item">
                <span className="step-number">2</span>
                <div className="step-content">
                  <strong>Face the camera</strong>
                  <p>Keep your head and shoulders relaxed within view of the webcam.</p>
                </div>
              </div>
              <div className="step-item">
                <span className="step-number">3</span>
                <div className="step-content">
                  <strong>Remain still for 3–5 seconds</strong>
                  <p>VisionGuard locks your individual anatomical proportions.</p>
                </div>
              </div>
            </div>
          ) : (
            <div className="calibration-steps">
              <div className="step-item">
                <span className="step-number">1</span>
                <div className="step-content">
                  <strong>Look comfortably toward your screen</strong>
                  <p>Keep your natural gaze toward the center of your monitor.</p>
                </div>
              </div>
              <div className="step-item">
                <span className="step-number">2</span>
                <div className="step-content">
                  <strong>Blink normally</strong>
                  <p>Do NOT unnaturally widen or strain your eyes; normal blinks are filtered.</p>
                </div>
              </div>
              <div className="step-item">
                <span className="step-number">3</span>
                <div className="step-content">
                  <strong>Remain relaxed</strong>
                  <p>Captures individual eye openness (EAR) and mouth geometry baselines.</p>
                </div>
              </div>
            </div>
          )}

          {isCollecting && (
            <div className="modal-collecting-state">
              <div className="collecting-pulse-banner">
                <span className="pulse-indicator" />
                <span>Calibrating baseline... Please remain still.</span>
              </div>
              <div className="calib-progress-bar-wrap">
                <div className="calib-progress-bar">
                  <div className="calib-progress-fill" style={{ width: `${progressPercent}%` }} />
                </div>
                <div className="calib-progress-meta">
                  <span>Progress: {progressPercent}%</span>
                  <span>{status.valid_samples} / {status.required_samples} samples</span>
                </div>
              </div>
            </div>
          )}

          {isCompleted && (
            <div className="modal-result-state completed">
              <div className="result-icon-check">&#10003;</div>
              <div className="result-text-group">
                <h4>Calibration Complete</h4>
                <p>Quality Rating: <span className="quality-pill">{status.quality || "EXCELLENT"}</span></p>
                <span className="result-sub">Baseline is active for real-time continuous analysis.</span>
              </div>
            </div>
          )}

          {isFailed && (
            <div className="modal-result-state failed">
              <div className="result-icon-warn">!</div>
              <div className="result-text-group">
                <h4>Calibration Incomplete</h4>
                <p className="error-reason">{status.failure_reason || "Could not collect stable baseline. Ensure good lighting and stay still."}</p>
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          {isCompleted ? (
            <div className="modal-btn-group">
              <button className="btn btn-secondary" onClick={onReset} disabled={isActionInProgress}>
                Reset Baseline
              </button>
              <button className="btn btn-primary" onClick={onClose}>
                Done
              </button>
            </div>
          ) : isCollecting ? (
            <button className="btn btn-secondary" onClick={onClose}>
              Cancel
            </button>
          ) : (
            <div className="modal-btn-group">
              <button className="btn btn-secondary" onClick={onClose}>
                Dismiss
              </button>
              <button className="btn btn-primary" onClick={onStart} disabled={isActionInProgress}>
                {isActionInProgress ? "Starting..." : isFailed ? "Try Again" : "Start Calibration"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
