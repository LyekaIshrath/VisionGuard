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
}

export const AlertnessCard: React.FC<AlertnessCardProps> = ({
  alertnessStatus,
  alertnessScore,
  humanState,
  calibration,
  canCalibrate,
  onOpenCalibration,
}) => {
  const isCalibrated = calibration.state === "COMPLETED";
  const closureSec = humanState.eye_closure_duration;
  const blinkRate = humanState.blink_rate;
  const yawnActive = (humanState.yawn_score || 0) > 0;

  return (
    <section className="dashboard-card telemetry-card" id="alertness-section" aria-label="Alertness and Drowsiness Intelligence">
      <div className="card-header">
        <div className="card-title-group">
          <h2 className="card-title">ALERTNESS</h2>
          <span className="card-subtitle">Multimodal Vigilance &amp; Eye Dynamics</span>
        </div>
        <StatusBadge type="alertness" value={alertnessStatus} />
      </div>

      <div className="telemetry-body">
        <div className="telemetry-stat-row">
          <div className="telemetry-main-val">
            <span className="stat-label">Vigilance State</span>
            <span className="stat-value">{alertnessStatus.replace(/_/g, " ")}</span>
          </div>
          <div className="telemetry-score-val">
            <span className="stat-label">Alertness Score</span>
            <span className="score-badge">
              <strong>{alertnessScore !== null ? alertnessScore : "—"}</strong>
              <span className="score-denom">/ 100</span>
            </span>
          </div>
        </div>

        {alertnessScore !== null && (
          <div className="stat-progress-wrapper">
            <div className="stat-progress-bar">
              <div
                className="stat-progress-fill good"
                style={{ width: `${Math.max(0, Math.min(100, alertnessScore))}%` }}
              />
            </div>
          </div>
        )}

        <div className="telemetry-grid-2x2">
          <div className="metric-box">
            <span className="metric-box-label">Eyes</span>
            <span className={`metric-box-val ${humanState.eye_state === "CLOSED" ? "warning" : ""}`}>
              {humanState.eye_state || "UNKNOWN"}
            </span>
          </div>
          <div className="metric-box">
            <span className="metric-box-label">Closure</span>
            <span className={`metric-box-val ${(closureSec || 0) >= 1.5 ? "warning" : ""}`}>
              {closureSec !== null && closureSec !== undefined ? `${closureSec.toFixed(1)} s` : "0.0 s"}
            </span>
          </div>
          <div className="metric-box">
            <span className="metric-box-label">Blink Rate</span>
            <span className="metric-box-val">
              {blinkRate !== null && blinkRate !== undefined ? `${blinkRate} / min` : "Collecting..."}
            </span>
          </div>
          <div className="metric-box">
            <span className="metric-box-label">Yawn Signal</span>
            <span className={`metric-box-val ${yawnActive ? "warning" : ""}`}>
              {yawnActive ? "Active" : "None"}
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
                <span className="calib-label">Calibration required for personal eye openness</span>
              </>
            )}
          </div>
          <button
            className="btn btn-secondary btn-sm calib-action-btn"
            disabled={!canCalibrate}
            onClick={onOpenCalibration}
          >
            {isCalibrated ? "Recalibrate" : "Calibrate"}
          </button>
        </div>

        <p className="card-helper-text">
          VisionGuard estimates observable alertness signals. It does not provide a medical diagnosis.
        </p>
      </div>
    </section>
  );
};
