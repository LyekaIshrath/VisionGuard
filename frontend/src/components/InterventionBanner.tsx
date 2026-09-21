import React from "react";
import { Intervention } from "../types";
import { StatusBadge } from "./StatusBadge";
import { useAlerts } from "../contexts/AlertContext";

interface InterventionBannerProps {
  intervention: Intervention | null;
}

function formatSafeTime(timestamp?: string | number | Date | null): string {
  if (!timestamp) return "--";
  try {
    const d = new Date(timestamp);
    return isNaN(d.getTime()) ? "--" : d.toLocaleTimeString();
  } catch {
    return "--";
  }
}

export const InterventionBanner: React.FC<InterventionBannerProps> = ({ intervention }) => {
  const { acknowledgeAlert, isAcknowledged } = useAlerts();

  if (!intervention || isAcknowledged(intervention.intervention_id)) {
    return (
      <section className="intervention-strip calm" aria-label="Active Wellness Intervention">
        <div className="intervention-calm-content">
          <span className="calm-icon" aria-hidden="true">&#10003;</span>
          <span className="calm-text">
            <strong>No active intervention</strong> &bull; VisionGuard is monitoring your posture and alertness signals.
          </span>
        </div>
      </section>
    );
  }

  const isHigh = intervention.level === "HIGH";

  return (
    <section className={`intervention-strip active ${isHigh ? "strip-high" : "strip-warning"}`} role="alert" aria-live="assertive">
      <div className="intervention-active-icon" aria-hidden="true">
        {isHigh ? "!" : "i"}
      </div>
      <div className="intervention-active-body">
        <div className="intervention-active-header">
          <span className="intervention-category-tag">{intervention.category} &bull; {intervention.level}</span>
          <span className="intervention-time">{formatSafeTime(intervention.timestamp)}</span>
        </div>
        <h4 className="intervention-title">{intervention.title}</h4>
        <p className="intervention-message">{intervention.message}</p>
      </div>
      <div className="intervention-badge-wrap" style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <StatusBadge type="risk" value={intervention.level} />
        <button
          className="btn btn-sm btn-secondary"
          onClick={() => acknowledgeAlert(intervention.intervention_id)}
          title="Acknowledge alert and hide banner"
        >
          Got it
        </button>
      </div>
    </section>
  );
};
