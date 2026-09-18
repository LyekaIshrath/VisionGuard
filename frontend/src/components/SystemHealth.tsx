import React from "react";
import { HumanStateData, MonitoringState } from "../types";

interface SystemHealthProps {
  monitoringState: MonitoringState;
  cameraState: string;
  backendConnected: boolean;
  wsConnected: boolean;
  framesReceived: number;
  humanState: HumanStateData;
}

export const SystemHealth: React.FC<SystemHealthProps> = ({
  monitoringState,
  cameraState,
  backendConnected,
  wsConnected,
  framesReceived,
  humanState,
}) => {
  const isCameraHealthy = cameraState === "READY";
  const isRunning = monitoringState === "RUNNING";

  return (
    <section className="health-strip" aria-label="System Health and Telemetry Status">
      <div className="health-item">
        <span className={`health-dot ${isCameraHealthy && isRunning ? "good" : cameraState === "NO_FRAMES" ? "warning" : cameraState === "CAMERA_ERROR" ? "danger" : "muted"}`} />
        <span className="health-label">CAMERA:</span>
        <span className="health-val">{isCameraHealthy ? "Ready" : cameraState === "NO_FRAMES" ? "No Frames" : cameraState === "CAMERA_ERROR" ? "Error" : "Standby"}</span>
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
