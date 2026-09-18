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
  const isCameraHealthy = cameraState === "READY";
  const isRunning = monitoringState === "RUNNING";
  const isBusyOrUnavailable = cameraState === "CAMERA_BUSY_OR_UNAVAILABLE" || cameraState === "CAMERA_ERROR";
  const isNoFrames = cameraState === "NO_FRAMES";

  const getCameraStatusLabel = () => {
    if (isCameraHealthy) return "Ready";
    if (isNoFrames) return "No Frames";
    if (cameraState === "CAMERA_BUSY_OR_UNAVAILABLE") return "Busy/Unavailable";
    if (cameraState === "CAMERA_ERROR") return "Error";
    return "Standby";
  };

  const getCameraStatusDotClass = () => {
    if (isCameraHealthy && isRunning) return "good";
    if (isNoFrames) return "warning";
    if (isBusyOrUnavailable) return "danger";
    return "muted";
  };

  return (
    <section className="health-strip" aria-label="System Health and Telemetry Status" onClick={onOpenStatus} style={{ cursor: onOpenStatus ? "pointer" : "default" }} title={onOpenStatus ? "Click to view System Status Center" : undefined}>
      <div className="health-item">
        <span className={`health-dot ${getCameraStatusDotClass()}`} />
        <span className="health-label">CAMERA:</span>
        <span className="health-val">{getCameraStatusLabel()}</span>
      </div>

      <div className="health-divider" />

      <div className="health-item">
        <span className={`health-dot ${humanState.person_detected ? "good" : "muted"}`} />
        <span className="health-label">PERSON:</span>
        <span className="health-val">{humanState.person_detected ? "Detected" : "Searching"}</span>
      </div>

      <div className="health-divider" />

      <div className="health-item">
        <span className={`health-dot ${humanState.face_detected ? "good" : "muted"}`} />
        <span className="health-label">FACE:</span>
        <span className="health-val">{humanState.face_detected ? "Detected" : "Searching"}</span>
      </div>

      <div className="health-divider" />

      <div className="health-item">
        <span className={`health-dot ${humanState.pose_detected ? "good" : "muted"}`} />
        <span className="health-label">POSE:</span>
        <span className="health-val">{humanState.pose_detected ? "Detected" : "Searching"}</span>
      </div>

      <div className="health-divider" />

      <div className="health-item">
        <span className={`health-dot ${wsConnected && backendConnected ? "good" : "warning"}`} />
        <span className="health-label">STREAM:</span>
        <span className="health-val">{wsConnected ? "Connected" : "Reconnecting"}</span>
      </div>

      <div className="health-divider" />

      <div className="health-item">
        <span className="health-dot good" />
        <span className="health-label">PROCESSING:</span>
        <span className="health-val">Local Edge</span>
      </div>

      {framesReceived > 0 && (
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
