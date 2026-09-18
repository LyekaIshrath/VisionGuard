import React from "react";
import { PostureStatus, CalibrationStatus } from "../types";
import { StatusBadge } from "./StatusBadge";

interface PostureCardProps {
  postureStatus: PostureStatus;
  postureScore: number | null;
  calibration: CalibrationStatus;
  canCalibrate: boolean;
  onOpenCalibration: () => void;
}

export const PostureCard: React.FC<PostureCardProps> = ({
  postureStatus,
  postureScore,
  calibration,
  canCalibrate,
  onOpenCalibration,
}) => {
  const isCalibrated = calibration.state === "COMPLETED";

  return (
    <section className="dashboard-card telemetry-card" id="posture-section" aria-label="Live Posture Analysis">
      <div className="card-header">
        <div className="card-title-group">
          <h2 className="card-title">POSTURE</h2>
          <span className="card-subtitle">Normalized 2D Biomechanical Geometry</span>
        </div>
        <StatusBadge type="posture" value={postureStatus} />
      </div>

      <div className="telemetry-body">
        <div className="telemetry-stat-row">
          <div className="telemetry-main-val">
            <span className="stat-label">Current Alignment</span>
            <span className="stat-value">{postureStatus.replace(/_/g, " ")}</span>
          </div>
          <div className="telemetry-score-val">
            <span className="stat-label">Posture Score</span>
            <span className="score-badge">
              <strong>{postureScore !== null ? postureScore : "—"}</strong>
              <span className="score-denom">/ 100</span>
            </span>
          </div>
        </div>

        {postureScore !== null && (
          <div className="stat-progress-wrapper">
            <div className="stat-progress-bar">
              <div
                className="stat-progress-fill good"
                style={{ width: `${Math.max(0, Math.min(100, postureScore))}%` }}
              />
            </div>
          </div>
        )}

        <div className="calibration-status-row">
          <div className="calib-indicator">
            {isCalibrated ? (
              <>
                <span className="calib-check" aria-hidden="true">&#10003;</span>
                <span className="calib-label">Calibrated • Quality: <strong>{calibration.quality || "EXCELLENT"}</strong></span>
              </>
            ) : (
              <>
                <span className="calib-dot warning" aria-hidden="true" />
                <span className="calib-label">Calibration required for personal upright baseline</span>
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
          Sit naturally in your preferred upright position. Baseline locks individual proportions.
        </p>
      </div>
    </section>
  );
};
