import React from "react";
import { HumanStateData, MonitoringState } from "../types";

interface SystemHealthProps {
  monitoringState: MonitoringState;
  cameraState: string;
  backendConnected: boolean;
  wsConnected: boolean;
  framesReceived: number;
  humanState: HumanStateData;
  onOpenStatus?: () => void;
}

export const SystemHealth: React.FC<SystemHealthProps> = ({
  monitoringState,
  cameraState,
  backendConnected,
  wsConnected,
  framesReceived,
  humanState,
  onOpenStatus,
}) => {
  const isRunning = monitoringState === "RUNNING";
  const isCameraHealthy = cameraState === "READY" || (isRunning && cameraState !== "CAMERA_ERROR");
  const isBusyOrUnavailable = cameraState === "CAMERA_BUSY_OR_UNAVAILABLE" || cameraState === "CAMERA_ERROR";
  const isNoFrames = cameraState === "NO_FRAMES";

  const getCameraStatusLabel = () => {
    if (!isRunning) return "STANDBY";
    if (isCameraHealthy) return "READY";
    if (isNoFrames) return "NO FRAMES";
    if (cameraState === "CAMERA_BUSY_OR_UNAVAILABLE") return "BUSY";
    if (cameraState === "CAMERA_ERROR") return "ERROR";
    return "STANDBY";
  };

  const getCameraStatusDotClass = () => {
    if (!isRunning) return "muted";
    if (isCameraHealthy) return "good";
    if (isNoFrames) return "warning";
    if (isBusyOrUnavailable) return "danger";
    return "muted";
  };

  // Semantically consistent stopped vs running detection state
  const personLabel = isRunning ? (humanState.person_detected ? "Detected" : "Searching") : "—";
  const personDotClass = isRunning ? (humanState.person_detected ? "good" : "muted") : "muted";

  const faceLabel = isRunning ? (humanState.face_detected ? "Detected" : "Searching") : "—";
  const faceDotClass = isRunning ? (humanState.face_detected ? "good" : "muted") : "muted";

  const poseLabel = isRunning ? (humanState.pose_detected ? "Detected" : "Searching") : "—";
  const poseDotClass = isRunning ? (humanState.pose_detected ? "good" : "muted") : "muted";

  const streamLabel = isRunning
    ? (wsConnected && backendConnected ? "Connected" : "Reconnecting")
    : "STANDBY";
  const streamDotClass = isRunning
    ? (wsConnected && backendConnected ? "good" : "warning")
    : "muted";

  return (
    <section
      className="health-strip"
      aria-label="System Health and Telemetry Status"
      onClick={onOpenStatus}
      style={{ cursor: onOpenStatus ? "pointer" : "default" }}
      title={onOpenStatus ? "Click to view System Status Center" : undefined}
    >
      <div className="health-item">
        <span className={`health-dot ${getCameraStatusDotClass()}`} />
        <span className="health-label">CAMERA:</span>
        <span className="health-val">{getCameraStatusLabel()}</span>
      </div>

      <div className="health-divider" />

      <div className="health-item">
        <span className={`health-dot ${personDotClass}`} />
        <span className="health-label">PERSON:</span>
        <span className="health-val">{personLabel}</span>
      </div>

      <div className="health-divider" />

      <div className="health-item">
        <span className={`health-dot ${faceDotClass}`} />
        <span className="health-label">FACE:</span>
        <span className="health-val">{faceLabel}</span>
      </div>

      <div className="health-divider" />

      <div className="health-item">
        <span className={`health-dot ${poseDotClass}`} />
        <span className="health-label">POSE:</span>
        <span className="health-val">{poseLabel}</span>
      </div>

      <div className="health-divider" />

      <div className="health-item">
        <span className={`health-dot ${streamDotClass}`} />
        <span className="health-label">STREAM:</span>
        <span className="health-val">{streamLabel}</span>
      </div>

      <div className="health-divider" />

      <div className="health-item">
        <span className="health-dot good" />
        <span className="health-label">PROCESSING:</span>
        <span className="health-val">LOCAL EDGE</span>
      </div>

      {isRunning && framesReceived > 0 && (
        <>
          <div className="health-divider" />
          <div className="health-item frames-counter">
            <span className="health-label">FRAMES:</span>
            <span className="health-val">{framesReceived.toLocaleString()}</span>
          </div>
        </>
      )}
    </section>
  );
};
