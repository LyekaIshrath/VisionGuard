import React, { useState } from "react";
import { formatDuration, formatSafeTime } from "./ReportFormatters";
import { ActivityInterval } from "./reportTypes";

interface SessionActivityBarProps {
  intervals?: ActivityInterval[];
  totalDurationSeconds: number;
}

export const SessionActivityBar: React.FC<SessionActivityBarProps> = ({
  intervals = [],
  totalDurationSeconds,
}) => {
  const [hoveredInterval, setHoveredInterval] = useState<ActivityInterval | null>(null);

  if (!intervals || intervals.length === 0) {
    return (
      <section className="report-section-root">
        <div className="report-section-header">
          <div className="report-section-title-group">
            <h2 className="report-section-title">Session Activity Bar</h2>
            <span className="report-section-subtitle">Continuous timeline of activity state segments</span>
          </div>
        </div>
        <div className="report-card report-empty-state">
          Activity intervals not available for this session.
        </div>
      </section>
    );
  }

  // Calculate sum of durations for proportional width
  const totalIntervalSec = intervals.reduce((acc, itv) => acc + (itv.duration_seconds || 0), 0);
  const baseDuration = Math.max(1, totalDurationSeconds > 0 ? totalDurationSeconds : totalIntervalSec);

  const getStateClass = (state: string) => {
    const s = (state || "").toUpperCase();
    if (s === "ENGAGED") return "bg-state-engaged";
    if (s === "OBSERVING") return "bg-state-observing";
    if (s === "ATTENTION_AWAY") return "bg-state-attention-away";
    if (s === "AWAY") return "bg-state-away";
    return "bg-state-unknown";
  };

  const getStateLabel = (state: string) => {
    const s = (state || "").toUpperCase();
    if (s === "ENGAGED") return "ENGAGED";
    if (s === "OBSERVING") return "OBSERVING";
    if (s === "ATTENTION_AWAY") return "ATTENTION AWAY";
    if (s === "AWAY") return "AWAY";
    return "UNKNOWN";
  };

  return (
    <section className="report-section-root">
      <div className="report-section-header flex-between">
        <div className="report-section-title-group">
          <h2 className="report-section-title">Session Activity Bar</h2>
          <span className="report-section-subtitle">
            Continuous chronological timeline of persisted activity intervals ({intervals.length} segments)
          </span>
        </div>
        <div className="activity-bar-legend">
          <span className="legend-item"><span className="legend-dot bg-state-engaged" />Engaged</span>
          <span className="legend-item"><span className="legend-dot bg-state-observing" />Observing</span>
          <span className="legend-item"><span className="legend-dot bg-state-attention-away" />Attention Away</span>
          <span className="legend-item"><span className="legend-dot bg-state-away" />Away</span>
          <span className="legend-item"><span className="legend-dot bg-state-unknown" />Unknown</span>
        </div>
      </div>

      <div className="report-card">
        {/* Continuous Bar */}
        <div className="activity-timebar-container">
          <div className="activity-timebar" role="region" aria-label="Session Activity Segments">
            {intervals.map((itv, idx) => {
              const widthPct = Math.max(0.8, ((itv.duration_seconds || 0) / baseDuration) * 100);
              const isHovered = hoveredInterval === itv;

              return (
                <div
                  key={itv.interval_id || idx}
                  className={`activity-timebar-segment ${getStateClass(itv.state)} ${isHovered ? "active-segment" : ""}`}
                  style={{ width: `${widthPct}%` }}
                  onMouseEnter={() => setHoveredInterval(itv)}
                  onMouseLeave={() => setHoveredInterval(null)}
                  onClick={() => setHoveredInterval(itv)}
                  title={`${getStateLabel(itv.state)}: ${formatDuration(itv.duration_seconds)}`}
                />
              );
            })}
          </div>

          <div className="activity-timebar-axis">
            <span>START</span>
            <span>{formatDuration(totalDurationSeconds)} MONITORED</span>
            <span>END</span>
          </div>
        </div>

        {/* Hover / Tap Inspection Details */}
        <div className="activity-segment-inspector">
          {hoveredInterval ? (
            <div className="inspector-content">
              <div className="inspector-header">
                <span className={`inspector-state-tag ${getStateClass(hoveredInterval.state)}`}>
                  {getStateLabel(hoveredInterval.state)}
                </span>
                <span className="inspector-duration">
                  {formatDuration(hoveredInterval.duration_seconds)} ({Math.round(hoveredInterval.duration_seconds)} seconds)
                </span>
              </div>
              <div className="inspector-meta">
                <span className="inspector-time">
                  {formatSafeTime(hoveredInterval.start_time, true)} – {formatSafeTime(hoveredInterval.end_time, true)}
                </span>
                {hoveredInterval.signals_summary?.reasons && hoveredInterval.signals_summary.reasons.length > 0 && (
                  <span className="inspector-reasons">
                    Signals: {hoveredInterval.signals_summary.reasons.join(", ")}
                  </span>
                )}
              </div>
            </div>
          ) : (
            <div className="inspector-placeholder">
              Hover or tap any segment in the bar above to inspect interval start/end timestamps and telemetry signals.
            </div>
          )}
        </div>
      </div>
    </section>
  );
};
