import React from "react";
import { formatDuration, formatPct } from "./ReportFormatters";
import { SessionDocument } from "./reportTypes";

interface EyeAlertnessProps {
  session: SessionDocument;
}

export const EyeAlertnessSection: React.FC<EyeAlertnessProps> = ({ session }) => {
  const dur = Math.max(1, session.duration_seconds || 1);
  const eyes = session.eye_summary || {};

  const blinkCount = eyes.blink_count ?? eyes.total_blinks ?? 0;
  const validEyeSec = eyes.valid_eye_tracking_seconds;
  const validEyePct = eyes.valid_eye_observation_pct ?? (validEyeSec != null ? (validEyeSec / dur) * 100 : null);

  const longestClosure = eyes.longest_closure_seconds ?? eyes.longest_eye_closure_seconds;
  const rawBlinkRate = eyes.blink_rate_per_min ?? eyes.blink_rate;

  // Rate logic: Denominator is strictly VALID EYE TRACKING TIME
  let displayRate = "—";
  let rateExplanation = "Insufficient valid eye-tracking time";

  if (validEyeSec != null && validEyeSec >= 5 && rawBlinkRate != null) {
    displayRate = `${rawBlinkRate.toFixed(1)} /min`;
    rateExplanation = `Calculated over ${formatDuration(validEyeSec)} of valid tracking`;
  } else if (validEyeSec != null && validEyeSec >= 5 && blinkCount > 0) {
    const calcRate = (blinkCount / validEyeSec) * 60;
    displayRate = `${calcRate.toFixed(1)} /min`;
    rateExplanation = `Calculated over ${formatDuration(validEyeSec)} of valid tracking`;
  }

  const alertnessRiskSec = session.alertness_risk_seconds ?? 0;

  if (!session.eye_summary) {
    return (
      <section className="report-section-root">
        <div className="report-section-header">
          <h2 className="report-section-title">Eye & Alertness Signals</h2>
        </div>
        <div className="report-card report-empty-state">
          Eye tracking data unavailable for this session.
        </div>
      </section>
    );
  }

  return (
    <section className="report-section-root">
      <div className="report-section-header">
        <div className="report-section-title-group">
          <h2 className="report-section-title">Eye & Alertness Signals</h2>
          <span className="report-section-subtitle">
            Ocular indicators and fatigue metrics referenced strictly to valid tracking duration
          </span>
        </div>
      </div>

      <div className="report-card">
        <div className="report-metric-grid-5">
          {/* Blink Count */}
          <div className="metric-cell">
            <span className="metric-cell-label">Blink Count</span>
            <span className="metric-cell-value text-sky">{blinkCount}</span>
            <span className="metric-cell-sub">Validated eye-blink events</span>
          </div>

          {/* Blink Rate */}
          <div className="metric-cell">
            <span className="metric-cell-label">Blink Rate</span>
            <span className="metric-cell-value text-sky">{displayRate}</span>
            <span className="metric-cell-sub">{rateExplanation}</span>
          </div>

          {/* Tracking Coverage */}
          <div className="metric-cell">
            <span className="metric-cell-label">Tracking Coverage</span>
            <span className="metric-cell-value">
              {validEyeSec != null ? formatDuration(validEyeSec) : "—"}
            </span>
            <span className="metric-cell-sub">
              {validEyePct != null ? `${formatPct(validEyePct)} of session` : "Not available"}
            </span>
          </div>

          {/* Longest Closure */}
          <div className="metric-cell">
            <span className="metric-cell-label">Longest Eye Closure</span>
            <span className="metric-cell-value">
              {longestClosure != null ? `${longestClosure.toFixed(2)}s` : "—"}
            </span>
            <span className="metric-cell-sub">Maximum continuous eye-closure</span>
          </div>

          {/* Alertness Risk Events */}
          <div className="metric-cell">
            <span className="metric-cell-label">Alertness Risk Events</span>
            <span className="metric-cell-value">
              {alertnessRiskSec > 0 ? formatDuration(alertnessRiskSec) : "0"}
            </span>
            <span className="metric-cell-sub">Sustained microsleep / drowsiness</span>
          </div>
        </div>
      </div>
    </section>
  );
};
