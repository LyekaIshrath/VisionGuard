import React from "react";
import { PostureStatus, AlertnessStatus, RiskLevel } from "../types";

interface StatusBadgeProps {
  type: "posture" | "alertness" | "risk" | "event";
  value: string;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ type, value, className = "" }) => {
  const formatText = (text: string) => {
    return text.replace(/_/g, " ");
  };

  const getBadgeClass = () => {
    if (type === "risk") {
      switch (value as RiskLevel) {
        case "LOW":
          return "badge-good";
        case "MODERATE":
          return "badge-warning";
        case "HIGH":
          return "badge-high";
        case "UNKNOWN":
        default:
          return "badge-unknown";
      }
    }

    if (type === "posture") {
      switch (value as PostureStatus) {
        case "GOOD":
          return "badge-good";
        case "SLOUCHING":
          return "badge-slouch";
        case "FORWARD_LEAN":
          return "badge-forward";
        case "LEFT_LEAN":
        case "RIGHT_LEAN":
          return "badge-lean";
        case "UNKNOWN":
          return "badge-unknown";
        case "NOT_CALIBRATED":
        default:
          return "badge-uncalibrated";
      }
    }

    if (type === "alertness") {
      switch (value as AlertnessStatus) {
        case "ALERT":
          return "badge-good";
        case "POSSIBLE_DROWSINESS":
          return "badge-drowsy";
        case "UNKNOWN":
          return "badge-unknown";
        case "NOT_CALIBRATED":
        default:
          return "badge-uncalibrated";
      }
    }

    if (type === "event") {
      if (value === "STARTED") return "badge-event-started";
      if (value === "RESOLVED") return "badge-event-resolved";
      return "badge-unknown";
    }

    return "badge-unknown";
  };

  return (
    <span className={`status-badge ${getBadgeClass()} ${className}`} aria-label={`${type}: ${formatText(value)}`}>
      <span className="badge-dot" aria-hidden="true" />
      <span className="badge-text">{formatText(value)}</span>
    </span>
  );
};
