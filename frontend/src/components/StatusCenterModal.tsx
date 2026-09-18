import React from "react";
import { MonitoringState } from "../types";

interface StatusCenterModalProps {
  isOpen: boolean;
  onClose: () => void;
  monitoringState: MonitoringState;
  cameraState: string;
  backendConnected: boolean;
  wsConnected: boolean;
  framesReceived: number;
  apiBase: string;
  appVersion?: string;
}

const StatusRow: React.FC<{
  label: string;
  value: string;
  status: "ok" | "warn" | "error" | "idle";
}> = ({ label, value, status }) => {
  const dotColor = {
    ok: "#22c55e",
    warn: "#f59e0b",
    error: "#ef4444",
    idle: "#64748b",
  }[status];

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "10px 0",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <span style={{ color: "#94a3b8", fontSize: "13px" }}>{label}</span>
      <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            backgroundColor: dotColor,
            display: "inline-block",
            boxShadow: `0 0 6px ${dotColor}88`,
          }}
        />
        <span style={{ color: "#e2e8f0", fontSize: "13px", fontWeight: 500 }}>{value}</span>
      </span>
    </div>
  );
};

export const StatusCenterModal: React.FC<StatusCenterModalProps> = ({
  isOpen,
  onClose,
  monitoringState,
  cameraState,
  backendConnected,
  wsConnected,
  framesReceived,
  apiBase,
  appVersion = "1.0.0",
}) => {
  if (!isOpen) return null;

  const isRunning = monitoringState === "RUNNING";
  const cameraOk = cameraState === "READY";
  const cameraStatus = cameraOk
    ? "ok"
    : cameraState === "NO_FRAMES"
    ? "warn"
    : cameraState === "CAMERA_ERROR" || cameraState === "CAMERA_BUSY_OR_UNAVAILABLE"
    ? "error"
    : "idle";

  const cameraLabel =
    cameraOk ? "Ready" :
    cameraState === "NO_FRAMES" ? "No Frames" :
    cameraState === "CAMERA_BUSY_OR_UNAVAILABLE" ? "Busy/Unavailable" :
    cameraState === "CAMERA_ERROR" ? "Error" : "Standby";

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0,0,0,0.65)",
        backdropFilter: "blur(6px)",
        zIndex: 9000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="System Status Center"
    >
      <div
        style={{
          background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
          border: "1px solid rgba(148,163,184,0.15)",
          borderRadius: "16px",
          padding: "28px 32px",
          width: "100%",
          maxWidth: "480px",
          boxShadow: "0 25px 60px rgba(0,0,0,0.6)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "24px",
          }}
        >
          <div>
            <h2
              style={{
                margin: 0,
                fontSize: "18px",
                fontWeight: 700,
                color: "#e2e8f0",
                letterSpacing: "0.03em",
              }}
            >
              System Status
            </h2>
            <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#64748b" }}>
              VisionGuard Local Companion v{appVersion}
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "1px solid rgba(148,163,184,0.2)",
              borderRadius: "8px",
              padding: "6px 10px",
              cursor: "pointer",
              color: "#64748b",
              fontSize: "12px",
            }}
            aria-label="Close Status Center"
          >
            ✕ Close
          </button>
        </div>

        {/* Section: Local Companion */}
        <div style={{ marginBottom: "20px" }}>
          <p
            style={{
              fontSize: "11px",
              fontWeight: 700,
              letterSpacing: "0.1em",
              color: "#475569",
              textTransform: "uppercase",
              margin: "0 0 4px",
            }}
          >
            Local Companion
          </p>
          <StatusRow label="Companion API" value={backendConnected ? "Connected" : "Disconnected"} status={backendConnected ? "ok" : "error"} />
          <StatusRow label="WebSocket Stream" value={wsConnected ? "Connected" : "Reconnecting"} status={wsConnected ? "ok" : "warn"} />
          <StatusRow label="Camera (OpenCV)" value={cameraLabel} status={cameraStatus} />
          <StatusRow label="Monitoring" value={isRunning ? "RUNNING" : "STOPPED"} status={isRunning ? "ok" : "idle"} />
          <StatusRow label="Frames Received" value={framesReceived.toLocaleString()} status={framesReceived > 0 ? "ok" : "idle"} />
        </div>

        {/* Section: Architecture */}
        <div style={{ marginBottom: "20px" }}>
          <p
            style={{
              fontSize: "11px",
              fontWeight: 700,
              letterSpacing: "0.1em",
              color: "#475569",
              textTransform: "uppercase",
              margin: "0 0 4px",
            }}
          >
            Architecture
          </p>
          <StatusRow label="Camera Mode" value="OpenCV (Python)" status="ok" />
          <StatusRow label="CV Inference" value="MediaPipe (Local)" status="ok" />
          <StatusRow label="Frame Storage" value="None — Privacy First" status="ok" />
          <StatusRow label="Cloud Transmission" value="Aggregates Only" status="ok" />
        </div>

        {/* PWA Status */}
        <div style={{ marginBottom: "8px" }}>
          <p
            style={{
              fontSize: "11px",
              fontWeight: 700,
              letterSpacing: "0.1em",
              color: "#475569",
              textTransform: "uppercase",
              margin: "0 0 4px",
            }}
          >
            PWA
          </p>
          <StatusRow
            label="PWA Installable"
            value="YES — Install from browser menu"
            status="ok"
          />
          <StatusRow
            label="Local Runtime Packaging"
            value="NOT IMPLEMENTED — run python -m app.main"
            status="idle"
          />
        </div>

        {/* API Base */}
        <div
          style={{
            marginTop: "20px",
            padding: "10px 14px",
            background: "rgba(255,255,255,0.04)",
            borderRadius: "8px",
            fontSize: "11px",
            color: "#475569",
          }}
        >
          Companion endpoint: <span style={{ color: "#94a3b8" }}>{apiBase}</span>
        </div>
      </div>
    </div>
  );
};
