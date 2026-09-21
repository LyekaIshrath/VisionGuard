import React from "react";
import { HumanStateData, MonitoringState } from "../types";
import { LiveCameraCard } from "./LiveCameraCard";
import { CurrentSessionCard } from "./CurrentSessionCard";
import { LiveActivityCard } from "./LiveActivityCard";
import { EventTimeline } from "./EventTimeline";

interface WorkMonitorViewProps {
  monitoringState: MonitoringState;
  cameraState: string;
  humanState: HumanStateData;
  previewKey: number;
  apiBase: string;
  sessionElapsedSec: number;
  latestReport: any;
  onOpenReport: () => void;
  eventHistory: any[];
  onClearHistory: () => void;
  onToggleMonitoring?: () => void;
  isStarting?: boolean;
}

export const WorkMonitorView: React.FC<WorkMonitorViewProps> = ({
  monitoringState,
  cameraState,
  humanState,
  previewKey,
  apiBase,
  sessionElapsedSec,
  latestReport,
  onOpenReport,
  eventHistory,
  onClearHistory,
  onToggleMonitoring,
  isStarting = false,
}) => {
  const isRunning = monitoringState === "RUNNING";

  return (
    <div
      className="view-container work-monitor-view"
      id="work-monitor"
      style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}
    >
      {/* Header Banner with Title, Actions & Direct Monitoring Controls */}
      <div
        className="view-header"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "1rem",
          paddingBottom: "1rem",
          borderBottom: "1px solid rgba(51, 65, 85, 0.4)",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h2
              className="view-title"
              style={{ fontSize: "1.6rem", fontWeight: 800, letterSpacing: "0.03em", margin: 0 }}
            >
              WORK MONITOR
            </h2>
            <span
              style={{
                padding: "2px 8px",
                borderRadius: "6px",
                fontSize: "11px",
                fontWeight: 700,
                background: isRunning ? "rgba(16, 185, 129, 0.2)" : "rgba(100, 116, 139, 0.2)",
                color: isRunning ? "#34d399" : "#94a3b8",
                border: `1px solid ${isRunning ? "rgba(16, 185, 129, 0.4)" : "rgba(100, 116, 139, 0.3)"}`,
              }}
            >
              {isRunning ? "MONITORING ACTIVE" : "STANDBY"}
            </span>
          </div>
          <p className="view-subtitle" style={{ color: "#94a3b8", fontSize: "0.875rem", marginTop: "4px", margin: 0 }}>
            Objective workstation telemetry &bull; Human-computer interaction tracking &bull; Zero calibration required
          </p>
        </div>

        {/* Action Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          {latestReport && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={onOpenReport}
              style={{ fontSize: "12px", padding: "6px 14px" }}
            >
              View Latest Report
            </button>
          )}

          {onToggleMonitoring && (
            <button
              className={`btn ${isRunning ? "btn-danger" : "btn-primary"}`}
              onClick={onToggleMonitoring}
              disabled={isStarting}
              style={{
                fontSize: "13px",
                padding: "8px 18px",
                fontWeight: 700,
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              {isStarting ? (
                <>
                  <span className="btn-spinner" aria-hidden="true" />
                  <span>Starting...</span>
                </>
              ) : isRunning ? (
                <>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                    <rect x="6" y="6" width="12" height="12" rx="2" />
                  </svg>
                  <span>STOP MONITORING</span>
                </>
              ) : (
                <>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                  <span>START MONITORING</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Primary Work Monitor Grid: Live Camera (Clean Geometry) + Current Session Card */}
      <div className="primary-grid" style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: "1.25rem" }}>
        <LiveCameraCard
          monitoringState={monitoringState}
          cameraState={cameraState}
          previewKey={previewKey}
          apiBase={apiBase}
          humanState={humanState}
        />

        <CurrentSessionCard
          monitoringState={monitoringState}
          humanState={humanState}
          sessionElapsedSec={sessionElapsedSec}
          onOpenReport={onOpenReport}
          hasReport={latestReport !== null}
        />
      </div>

      {/* Secondary Work Detail Grid: Live Activity Card + Workstation Observation Principles */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.25rem" }}>
        <LiveActivityCard
          humanState={humanState}
          monitoringState={monitoringState}
        />

        {/* Work Observation Rules & Principles Card */}
        <div
          className="dashboard-card"
          style={{
            padding: "1.25rem",
            background: "linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%)",
            borderRadius: "0.75rem",
            border: "1px solid rgba(51, 65, 85, 0.6)",
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
          }}
        >
          <h3
            style={{
              margin: 0,
              fontSize: "0.95rem",
              fontWeight: 600,
              color: "#f1f5f9",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            Observation Principles
          </h3>
          <p style={{ fontSize: "0.8rem", color: "#94a3b8", margin: 0, lineHeight: 1.5 }}>
            Work Activity tracks physical interaction states objectively without evaluative performance judgments:
          </p>
          <ul style={{ fontSize: "0.78rem", color: "#cbd5e1", margin: 0, paddingLeft: "1.25rem", lineHeight: 1.6 }}>
            <li>
              <strong>ENGAGED:</strong> Person present at workstation with recent input/interaction (&lt;15s).
            </li>
            <li>
              <strong>OBSERVING:</strong> Person present, facing display, reading, reviewing code, or thinking.
            </li>
            <li>
              <strong>ATTENTION AWAY:</strong> Person present with sustained head yaw turned away (&ge;8s).
            </li>
            <li>
              <strong>AWAY:</strong> Person absent from workstation (&ge;5s).
            </li>
            <li>
              <strong>Screen changes &amp; blinks</strong> serve as supportive context; they never independently trigger states.
            </li>
          </ul>
          <div
            style={{
              marginTop: "auto",
              paddingTop: "0.5rem",
              borderTop: "1px solid rgba(51, 65, 85, 0.4)",
              fontSize: "0.72rem",
              color: "#64748b",
            }}
          >
            Zero keylogging &bull; Zero screenshots saved &bull; Instant startup with built-in baseline
          </div>
        </div>
      </div>

      {/* Session Event Timeline */}
      <div style={{ marginTop: "0.5rem" }}>
        <EventTimeline events={eventHistory} onClearHistory={onClearHistory} />
      </div>
    </div>
  );
};
