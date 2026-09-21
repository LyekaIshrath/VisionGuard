import React, { useState } from "react";
import { HumanStateData, MonitoringState } from "../types";

export type OverlayModeType = "OFF" | "MINIMAL" | "DEBUG";

interface LiveCameraCardProps {
  monitoringState: MonitoringState;
  cameraState: string;
  previewKey: number;
  apiBase: string;
  humanState: HumanStateData;
}

export const LiveCameraCard: React.FC<LiveCameraCardProps> = ({
  monitoringState,
  cameraState,
  previewKey,
  apiBase,
  humanState,
}) => {
  const isRunning = monitoringState === "RUNNING";
  const isCameraReady = cameraState === "LIVE" || cameraState === "READY";
  const isBusyOrUnavailable = cameraState === "CAMERA_BUSY" || cameraState === "CAMERA_BUSY_OR_UNAVAILABLE" || cameraState === "NO_CAMERA" || cameraState === "ERROR" || cameraState === "CAMERA_ERROR";
  const isNoFrames = cameraState === "NO_FRAMES";
  const [overlayMode, setOverlayMode] = useState<OverlayModeType>("MINIMAL");

  return (
    <section className="dashboard-card camera-card" id="live-camera" aria-label="Live Camera Monitoring">
      <div className="card-header">
        <div className="card-title-group">
          <h2 className="card-title">LIVE CAMERA</h2>
          <span className="card-subtitle">Local Camera Feed &bull; Clean Geometry</span>
        </div>
        <div className="card-header-actions">
          {isRunning && isCameraReady && (
            <span className="live-indicator">
              <span className="live-dot" />
              <span>LIVE</span>
            </span>
          )}
          <span className="privacy-badge" title="Frames are analyzed locally on device and are never stored or uploaded.">
            LOCAL PROCESSING
          </span>
        </div>
      </div>

      <div className="camera-viewport-container">
        {isRunning ? (
          isCameraReady ? (
            <div className="camera-feed-wrapper">
              <img
                src={`${apiBase}/api/v1/monitoring/preview?overlay=${overlayMode}&t=${previewKey}`}
                alt="Live camera feed with clean human geometry overlay"
                className="camera-video-feed"
              />
              <div className="camera-overlay-top">
                <span className="overlay-badge live">
                  ● LIVE {typeof humanState.preview_fps === "number" && humanState.preview_fps > 0 ? `${humanState.preview_fps.toFixed(0)} FPS` : (typeof humanState.capture_fps === "number" && humanState.capture_fps > 0 ? `${humanState.capture_fps.toFixed(0)} FPS` : "LIVE")}
                </span>
              </div>
              <div className="camera-overlay-bottom">
                <div className="detection-pills">
                  <span className={`det-pill ${humanState.person_detected || humanState.person_present ? "detected" : ""}`}>
                    <span className="det-dot" /> Person
                  </span>
                  <span className={`det-pill ${humanState.face_detected ? "detected" : ""}`}>
                    <span className="det-dot" /> Face
                  </span>
                  <span className={`det-pill ${humanState.pose_detected ? "detected" : ""}`}>
                    <span className="det-dot" /> Pose
                  </span>
                </div>
              </div>
            </div>
          ) : isBusyOrUnavailable ? (
            <div className="camera-placeholder error">
              <div className="placeholder-icon warning" aria-hidden="true">
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="1.8">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
              </div>
              <p className="placeholder-title">Camera Busy or Unavailable</p>
              <p className="placeholder-sub">The local application cannot access the webcam. Ensure no other application (Zoom, Teams, etc.) is holding the camera.</p>
            </div>
          ) : isNoFrames ? (
            <div className="camera-placeholder warning">
              <div className="placeholder-icon warning" aria-hidden="true">
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="1.8">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
              </div>
              <p className="placeholder-title">No Video Frames Received</p>
              <p className="placeholder-sub">The camera device was opened, but video frame acquisition timed out (&gt;1500ms). Reconnect attempt active.</p>
            </div>
          ) : (
            <div className="camera-placeholder connecting">
              <div className="placeholder-spinner" aria-hidden="true" />
              <p className="placeholder-title">Connecting to camera capture...</p>
              <p className="placeholder-sub">Acquiring video frames from integrated webcam.</p>
            </div>
          )
        ) : (
          <div className="camera-placeholder standby">
            <div className="placeholder-icon" aria-hidden="true">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M23 7l-7 5 7 5V7z" />
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
              </svg>
            </div>
            <p className="placeholder-title">Camera Monitoring is Standby</p>
            <p className="placeholder-sub">Click "START MONITORING" to begin tracking your work session.</p>
          </div>
        )}
      </div>

      <div className="card-footer camera-footer">
        <div className="overlay-selector-container">
          <span className="overlay-selector-label">Geometry Overlay</span>
          <div className="overlay-pill-group" role="radiogroup" aria-label="Overlay Mode">
            <button
              type="button"
              role="radio"
              aria-checked={overlayMode === "OFF"}
              className={`overlay-pill-btn ${overlayMode === "OFF" ? "active" : ""}`}
              onClick={() => setOverlayMode("OFF")}
              title="Raw camera stream without annotations"
            >
              OFF
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={overlayMode === "MINIMAL"}
              className={`overlay-pill-btn ${overlayMode === "MINIMAL" ? "active" : ""}`}
              onClick={() => setOverlayMode("MINIMAL")}
              title="Clean geometry skeleton, head axis, and alignment points"
            >
              CLEAN GEOMETRY
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={overlayMode === "DEBUG"}
              className={`overlay-pill-btn ${overlayMode === "DEBUG" ? "active" : ""}`}
              onClick={() => setOverlayMode("DEBUG")}
              title="Detailed telemetry metrics and thresholds"
            >
              DETAILED
            </button>
          </div>
        </div>

        <div className="privacy-note">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
          <span>Local Processing &bull; Zero Frames Stored</span>
        </div>
      </div>
    </section>
  );
};
