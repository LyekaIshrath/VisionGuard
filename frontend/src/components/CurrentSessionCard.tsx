import React from "react";
import { HumanStateData, MonitoringState } from "../types";
import { formatDuration } from "../utils/format";

interface CurrentSessionCardProps {
  monitoringState: MonitoringState;
  humanState: HumanStateData;
  sessionElapsedSec: number;
  onOpenReport?: () => void;
  hasReport?: boolean;
}

export const CurrentSessionCard: React.FC<CurrentSessionCardProps> = ({
  monitoringState,
  humanState,
  sessionElapsedSec,
  onOpenReport,
  hasReport = false,
}) => {
  const isRunning = monitoringState === "RUNNING";
  const activityState = humanState.activity_state || "UNKNOWN";
  const personPresent = humanState.person_detected || humanState.person_present || false;
  const screenLevel = humanState.screen_activity_level || "UNKNOWN";
  const idleSec = Math.round(humanState.idle_seconds ?? 0);
  const keyEvents = humanState.keyboard_activity_count ?? 0;
  const mouseEvents = humanState.mouse_activity_count ?? 0;
  const clicks = humanState.mouse_click_count ?? 0;
  const scrolls = humanState.scroll_count ?? 0;
  const blinks = humanState.blink_count ?? 0;
  const postureStatus = humanState.posture_status || "GOOD";
  const eyesClosed = humanState.eyes_closed === true;

  const getActivityBadgeClass = () => {
    switch (activityState) {
      case "ENGAGED":
      case "ACTIVE":
        return "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
      case "OBSERVING":
      case "LOW_ACTIVITY":
        return "bg-sky-500/20 text-sky-300 border-sky-500/40";
      case "ATTENTION_AWAY":
        return "bg-amber-500/20 text-amber-300 border-amber-500/40";
      case "AWAY":
        return "bg-slate-700/40 text-slate-400 border-slate-600/40";
      default:
        return "bg-slate-800 text-slate-400 border-slate-700";
    }
  };

  return (
    <section className="dashboard-card" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Card Header */}
      <div className="card-header">
        <div className="card-title-group">
          <h2 className="card-title">CURRENT SESSION</h2>
          <span className="card-subtitle">Live Workstation & Activity Metrics</span>
        </div>
        <div className="card-header-actions">
          {hasReport && (
            <button
              onClick={onOpenReport}
              className="btn btn-secondary btn-sm"
              style={{ fontSize: "11px", padding: "4px 10px" }}
            >
              View Report
            </button>
          )}
        </div>
      </div>

      {/* Main Stats Body */}
      <div style={{ padding: "1.25rem", flex: 1, display: "flex", flexDirection: "column", gap: "1.25rem" }}>
        {/* Session Timer & State Strip */}
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "1rem",
          background: "rgba(15, 23, 42, 0.6)",
          borderRadius: "12px",
          border: "1px solid rgba(51, 65, 85, 0.4)"
        }}>
          <div>
            <span style={{ fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.05em", color: "#94a3b8", fontWeight: 600 }}>
              Session Duration
            </span>
            <div style={{ fontSize: "1.75rem", fontWeight: 800, fontFamily: "monospace", color: isRunning ? "#38bdf8" : "#94a3b8", marginTop: "2px" }}>
              {formatDuration(sessionElapsedSec)}
            </div>
          </div>

          <div style={{ textAlign: "right" }}>
            <span style={{ fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.05em", color: "#94a3b8", fontWeight: 600 }}>
              Activity State
            </span>
            <div style={{ marginTop: "4px" }}>
              <span className={`px-2.5 py-1 text-xs font-bold rounded-full border ${getActivityBadgeClass()}`}>
                {isRunning ? activityState : "STOPPED"}
              </span>
            </div>
          </div>
        </div>

        {/* 2x2 Primary Signals Grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
          {/* Presence */}
          <div style={{ padding: "0.75rem", background: "rgba(30, 41, 59, 0.4)", borderRadius: "8px", border: "1px solid rgba(51, 65, 85, 0.3)" }}>
            <span style={{ fontSize: "11px", color: "#94a3b8", fontWeight: 500 }}>Person Presence</span>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", marginTop: "4px" }}>
              <span style={{
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                background: personPresent ? "#10b981" : "#ef4444"
              }} />
              <span style={{ fontSize: "14px", fontWeight: 700, color: personPresent ? "#10b981" : "#ef4444" }}>
                {personPresent ? "Present" : "Away"}
              </span>
            </div>
          </div>

          {/* Screen Activity */}
          <div style={{ padding: "0.75rem", background: "rgba(30, 41, 59, 0.4)", borderRadius: "8px", border: "1px solid rgba(51, 65, 85, 0.3)" }}>
            <span style={{ fontSize: "11px", color: "#94a3b8", fontWeight: 500 }}>Screen Change</span>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", marginTop: "4px" }}>
              <span style={{
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                background: screenLevel === "CHANGING" ? "#38bdf8" : screenLevel === "LOW_CHANGE" ? "#10b981" : "#64748b"
              }} />
              <span style={{ fontSize: "14px", fontWeight: 700, color: "#e2e8f0" }}>
                {screenLevel}
              </span>
            </div>
          </div>

          {/* Eyes & Blinks */}
          <div style={{ padding: "0.75rem", background: "rgba(30, 41, 59, 0.4)", borderRadius: "8px", border: "1px solid rgba(51, 65, 85, 0.3)" }}>
            <span style={{ fontSize: "11px", color: "#94a3b8", fontWeight: 500 }}>Eyes & Blinks</span>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "4px" }}>
              <span style={{ fontSize: "13px", fontWeight: 600, color: eyesClosed ? "#f59e0b" : "#10b981" }}>
                {eyesClosed ? "Closed" : "Open"}
              </span>
              <span style={{ fontSize: "12px", color: "#94a3b8", fontFamily: "monospace" }}>
                {blinks} blinks
              </span>
            </div>
          </div>

          {/* Posture */}
          <div style={{ padding: "0.75rem", background: "rgba(30, 41, 59, 0.4)", borderRadius: "8px", border: "1px solid rgba(51, 65, 85, 0.3)" }}>
            <span style={{ fontSize: "11px", color: "#94a3b8", fontWeight: 500 }}>Posture Alignment</span>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", marginTop: "4px" }}>
              <span style={{
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                background: postureStatus === "GOOD" ? "#10b981" : "#f59e0b"
              }} />
              <span style={{ fontSize: "14px", fontWeight: 700, color: postureStatus === "GOOD" ? "#10b981" : "#f59e0b" }}>
                {postureStatus}
              </span>
            </div>
          </div>
        </div>

        {/* Workstation Activity (Zero Keylogging) */}
        <div style={{
          padding: "1rem",
          background: "rgba(15, 23, 42, 0.4)",
          borderRadius: "10px",
          border: "1px solid rgba(51, 65, 85, 0.3)"
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <span style={{ fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.05em", color: "#94a3b8", fontWeight: 600 }}>
              Computer Input Activity
            </span>
            <span style={{ fontSize: "10px", color: "#64748b" }}>Privacy Preserved</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.5rem", textAlign: "center" }}>
            <div style={{ background: "rgba(30, 41, 59, 0.5)", padding: "0.5rem", borderRadius: "6px" }}>
              <div style={{ fontSize: "11px", color: "#94a3b8" }}>Keys</div>
              <div style={{ fontSize: "14px", fontWeight: 700, color: "#e2e8f0", marginTop: "2px" }}>{keyEvents}</div>
            </div>
            <div style={{ background: "rgba(30, 41, 59, 0.5)", padding: "0.5rem", borderRadius: "6px" }}>
              <div style={{ fontSize: "11px", color: "#94a3b8" }}>Moves</div>
              <div style={{ fontSize: "14px", fontWeight: 700, color: "#e2e8f0", marginTop: "2px" }}>{mouseEvents}</div>
            </div>
            <div style={{ background: "rgba(30, 41, 59, 0.5)", padding: "0.5rem", borderRadius: "6px" }}>
              <div style={{ fontSize: "11px", color: "#94a3b8" }}>Clicks / Scrolls</div>
              <div style={{ fontSize: "14px", fontWeight: 700, color: "#e2e8f0", marginTop: "2px" }}>{clicks} / {scrolls}</div>
            </div>
            <div style={{ background: "rgba(30, 41, 59, 0.5)", padding: "0.5rem", borderRadius: "6px" }}>
              <div style={{ fontSize: "11px", color: "#94a3b8" }}>Idle</div>
              <div style={{ fontSize: "14px", fontWeight: 700, color: idleSec > 30 ? "#f59e0b" : "#e2e8f0", marginTop: "2px" }}>{idleSec}s</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
