import React from "react";
import { formatDuration, formatPct } from "./ReportFormatters";
import { SessionDocument } from "./reportTypes";

interface ScreenActivityProps {
  session: SessionDocument;
}

export const ScreenActivitySection: React.FC<ScreenActivityProps> = ({ session }) => {
  const dur = Math.max(1, session.duration_seconds || 1);
  const scr = session.screen_summary || {};

  const changingSec = scr.screen_active_seconds ?? scr.changing_seconds ?? 0;
  const changingPct = scr.changing_pct ?? (changingSec / dur) * 100;

  const stableSec = (scr.static_seconds ?? 0) + (scr.low_change_seconds ?? 0);
  const stablePct = (scr.static_pct ?? 0) + (scr.low_change_pct ?? 0) || ((stableSec / dur) * 100);

  const unavailableSec = scr.unknown_seconds ?? Math.max(0, dur - changingSec - stableSec);
  const unavailablePct = scr.unknown_pct ?? (unavailableSec / dur) * 100;

  return (
    <section className="report-section-root">
      <div className="report-section-header">
        <div className="report-section-title-group">
          <h2 className="report-section-title">Screen Activity</h2>
          <span className="report-section-subtitle">
            Visual display frame delta signals without screen capture or content logging
          </span>
        </div>
      </div>

      <div className="report-card">
        <div className="report-metric-grid-3">
          <div className="metric-cell">
            <span className="metric-cell-label">Screen Changing</span>
            <span className="metric-cell-value text-teal">{formatDuration(changingSec)}</span>
            <span className="metric-cell-sub">{formatPct(changingPct)} of monitored session</span>
          </div>
          <div className="metric-cell">
            <span className="metric-cell-label">Screen Stable</span>
            <span className="metric-cell-value text-muted">{formatDuration(stableSec)}</span>
            <span className="metric-cell-sub">{formatPct(stablePct)} of monitored session</span>
          </div>
          <div className="metric-cell">
            <span className="metric-cell-label">Tracking Unavailable</span>
            <span className="metric-cell-value text-muted">{formatDuration(unavailableSec)}</span>
            <span className="metric-cell-sub">{formatPct(unavailablePct)} of monitored session</span>
          </div>
        </div>
      </div>
    </section>
  );
};
