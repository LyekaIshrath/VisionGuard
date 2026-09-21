import React from "react";
import { HumanStateData, WorkActivityState } from "../types";

interface LiveActivityCardProps {
  humanState: HumanStateData;
  monitoringState: string;
}

export const LiveActivityCard: React.FC<LiveActivityCardProps> = ({
  humanState,
  monitoringState,
}) => {
  const isMonitoring = monitoringState === "RUNNING";
  const state: WorkActivityState = (humanState.activity_state || "UNKNOWN") as WorkActivityState;
  const personPresent = humanState.person_detected || humanState.person_present || false;
  const idleSec = Math.round(humanState.idle_seconds ?? 0);
  const headYaw = humanState.head_yaw != null ? Math.round(Math.abs(humanState.head_yaw)) : null;
  const isHeadAligned = headYaw != null ? headYaw < 25 : personPresent;
  const keyEvents = humanState.keyboard_activity_count ?? 0;
  const mouseEvents = humanState.mouse_activity_count ?? 0;
  const blinks = humanState.blink_count ?? 0;

  const getStateBadge = () => {
    if (!isMonitoring) {
      return {
        label: "STANDBY",
        color: "bg-slate-700/60 text-slate-300 border-slate-600",
        description: "Start monitoring to track live session activity",
      };
    }
    switch (state) {
      case "ACTIVE":
        return {
          label: "ACTIVE",
          color: "bg-emerald-500/20 text-emerald-300 border-emerald-500/50",
          description: "Active physical input and workstation interaction",
        };
      case "LOW_ACTIVITY":
        return {
          label: "LOW ACTIVITY",
          color: "bg-sky-500/20 text-sky-300 border-sky-500/50",
          description: "Reading, thinking, or reviewing workstation content",
        };
      case "ATTENTION_AWAY":
        return {
          label: "ATTENTION AWAY",
          color: "bg-amber-500/20 text-amber-300 border-amber-500/50",
          description: "Sustained head orientation away from workstation",
        };
      case "AWAY":
        return {
          label: "AWAY",
          color: "bg-rose-500/20 text-rose-300 border-rose-500/50",
          description: "User absent from workstation",
        };
      default:
        return {
          label: "UNKNOWN",
          color: "bg-slate-600/20 text-slate-400 border-slate-600/40",
          description: "Insufficient optical or input signals",
        };
    }
  };

  const badge = getStateBadge();

  return (
    <div className="card live-activity-card" style={{
      background: "linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%)",
      borderRadius: "0.75rem",
      border: "1px solid rgba(51, 65, 85, 0.6)",
      padding: "1.25rem",
      display: "flex",
      flexDirection: "column",
      gap: "1rem",
      boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.2)",
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h3 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 600, color: "#f1f5f9", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Work Activity
          </h3>
          <span style={{ fontSize: "0.75rem", color: "#94a3b8" }}>
            Observable Workstation Interaction
          </span>
        </div>
        <div
          style={{
            padding: "0.25rem 0.75rem",
            borderRadius: "9999px",
            fontSize: "0.75rem",
            fontWeight: 700,
            letterSpacing: "0.05em",
            border: "1px solid",
          }}
          className={badge.color}
        >
          {badge.label}
        </div>
      </div>

      <p style={{ margin: 0, fontSize: "0.8rem", color: "#cbd5e1" }}>
        {badge.description}
      </p>

      {/* Observable Evidence Grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(2, 1fr)",
        gap: "0.75rem",
        background: "rgba(15, 23, 42, 0.4)",
        padding: "0.75rem",
        borderRadius: "0.5rem",
        border: "1px solid rgba(51, 65, 85, 0.4)"
      }}>
        {/* Evidence 1: Person Present */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
          <span style={{ fontSize: "0.7rem", color: "#94a3b8", textTransform: "uppercase" }}>Person Present</span>
          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span style={{
              width: "8px",
              height: "8px",
              borderRadius: "50%",
              background: personPresent ? "#10b981" : "#ef4444",
              display: "inline-block"
            }} />
            <strong style={{ fontSize: "0.85rem", color: "#f8fafc" }}>
              {personPresent ? "Detected" : "Absent"}
            </strong>
          </div>
        </div>

        {/* Evidence 2: Recent Input */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
          <span style={{ fontSize: "0.7rem", color: "#94a3b8", textTransform: "uppercase" }}>Recent Input</span>
          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <strong style={{ fontSize: "0.85rem", color: "#f8fafc" }}>
              {idleSec <= 5 ? "Active (<5s)" : `${idleSec}s ago`}
            </strong>
          </div>
          <span style={{ fontSize: "0.68rem", color: "#64748b" }}>
            Keys: {keyEvents} &bull; Mouse: {mouseEvents}
          </span>
        </div>

        {/* Evidence 3: Head Alignment */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
          <span style={{ fontSize: "0.7rem", color: "#94a3b8", textTransform: "uppercase" }}>Head Alignment</span>
          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span style={{
              width: "8px",
              height: "8px",
              borderRadius: "50%",
              background: isHeadAligned ? "#10b981" : "#f59e0b",
              display: "inline-block"
            }} />
            <strong style={{ fontSize: "0.85rem", color: "#f8fafc" }}>
              {isHeadAligned ? "At Screen" : "Looking Away"}
            </strong>
          </div>
        </div>

        {/* Evidence 4: Idle Time / Blinks */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
          <span style={{ fontSize: "0.7rem", color: "#94a3b8", textTransform: "uppercase" }}>Idle Time &amp; Blinks</span>
          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <strong style={{ fontSize: "0.85rem", color: "#f8fafc" }}>
              {idleSec}s idle
            </strong>
          </div>
          <span style={{ fontSize: "0.68rem", color: "#64748b" }}>
            Blink Count: {blinks}
          </span>
        </div>
      </div>

      {/* Privacy Notice */}
      <div style={{ fontSize: "0.7rem", color: "#64748b", borderTop: "1px solid rgba(51, 65, 85, 0.4)", paddingTop: "0.5rem" }}>
        <span>Privacy: Signals are derived locally. Zero keylogging, zero screenshots, zero judgment.</span>
      </div>
    </div>
  );
};
