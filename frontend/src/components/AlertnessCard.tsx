import React from "react";
import { AlertnessStatus, AlertnessCalibrationStatus, HumanStateData } from "../types";
import { StatusBadge } from "./StatusBadge";

interface AlertnessCardProps {
  alertnessStatus: AlertnessStatus;
  alertnessScore: number | null;
  humanState: HumanStateData;
  calibration: AlertnessCalibrationStatus;
  canCalibrate: boolean;
  onOpenCalibration: () => void;
  isRunning?: boolean;
}

export const AlertnessCard: React.FC<AlertnessCardProps> = ({
  alertnessStatus,
  alertnessScore,
  humanState,
  calibration,
  canCalibrate,
  onOpenCalibration,
  isRunning = true,
}) => {
  const isCalibrated = calibration.state === "COMPLETED";
  const closureSec = isRunning ? humanState.eye_closure_duration : null;
  const blinkRate = isRunning ? humanState.blink_rate : null;
  const yawnActive = isRunning && (humanState.yawn_score || 0) > 0;
  const displayStatus = isRunning ? alertnessStatus : "NO_ACTIVE_SESSION";
  const displayScore = isRunning && alertnessScore !== null ? alertnessScore : null;

  return (
    <section className="dashboard-card telemetry-card" id="alertness-section" aria-label="Alertness and Drowsiness Intelligence">
      <div className="card-header">
        <div className="card-title-group">
          <h2 className="card-title">ALERTNESS</h2>
          <span className="card-subtitle">Multimodal Vigilance &amp; Eye Dynamics</span>
        </div>
        <StatusBadge type="alertness" value={displayStatus} />
      </div>

      <div className="telemetry-body">
        <div className="telemetry-stat-row">
          <div className="telemetry-main-val">
            <span className="stat-label">Vigilance State</span>
            <span className="stat-value">{isRunning ? alertnessStatus.replace(/_/g, " ") : "NO ACTIVE SESSION"}</span>
          </div>
          <div className="telemetry-score-val">
            <span className="stat-label">Alertness Score</span>
            <span className="score-badge">
              <strong>{displayScore !== null ? displayScore : "—"}</strong>
              <span className="score-denom">/ 100</span>
            </span>
          </div>
        </div>

        {displayScore !== null && (
          <div className="stat-progress-wrapper">
            <div className="stat-progress-bar">
              <div
                className="stat-progress-fill good"
                style={{ width: `${Math.max(0, Math.min(100, displayScore))}%` }}
              />
            </div>
          </div>
        )}

        <div className="telemetry-grid-2x2">
          <div className="metric-box">
            <span className="metric-box-label">Eyes</span>
            <span className={`metric-box-val ${isRunning && humanState.eye_state === "CLOSED" ? "warning" : ""}`}>
              {isRunning ? (humanState.eye_state || "UNKNOWN") : "—"}
            </span>
          </div>
          <div className="metric-box">
            <span className="metric-box-label">Closure</span>
            <span className={`metric-box-val ${isRunning && (closureSec || 0) >= 1.5 ? "warning" : ""}`}>
              {isRunning && closureSec !== null && closureSec !== undefined ? `${closureSec.toFixed(1)} s` : "—"}
            </span>
          </div>
          <div className="metric-box">
            <span className="metric-box-label">Blink Rate</span>
            <span className="metric-box-val">
              {isRunning && blinkRate !== null && blinkRate !== undefined ? `${blinkRate} / min` : "—"}
            </span>
          </div>
          <div className="metric-box">
            <span className="metric-box-label">Yawn Signal</span>
            <span className={`metric-box-val ${yawnActive ? "warning" : ""}`}>
              {isRunning ? (yawnActive ? "Active" : "None") : "—"}
            </span>
          </div>
        </div>

        <div className="calibration-status-row">
          <div className="calib-indicator">
            {isCalibrated ? (
              <>
                <span className="calib-check" aria-hidden="true">&#10003;</span>
                <span className="calib-label">Calibrated • Quality: <strong>{calibration.quality || "GOOD"}</strong></span>
              </>
            ) : (
              <>
                <span className="calib-dot warning" aria-hidden="true" />
                <span className="calib-label">Built-in Engineering Baseline</span>
              </>
            )}
          </div>
          <button
            className="btn btn-secondary btn-sm calib-action-btn"
            disabled={!canCalibrate}
            onClick={onOpenCalibration}
          >
            {isCalibrated ? "Recalibrate Baseline" : "Personalize Baseline"}
          </button>
        </div>

        <p className="card-helper-text">
          VisionGuard estimates observable alertness signals. It does not provide a medical diagnosis.
        </p>
      </div>
    </section>
  );
};
