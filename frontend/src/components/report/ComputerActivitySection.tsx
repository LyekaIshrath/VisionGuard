import React from "react";
import { formatDuration } from "./ReportFormatters";
import { SessionDocument } from "./reportTypes";

interface ComputerActivityProps {
  session: SessionDocument;
}

export const ComputerActivitySection: React.FC<ComputerActivityProps> = ({ session }) => {
  const comp = session.computer_summary || {};

  const inputEvents = comp.keyboard_events ?? comp.keystrokes ?? 0;
  const mouseMovements = comp.mouse_movements ?? comp.mouse_moves ?? 0;
  const clicks = comp.mouse_clicks ?? comp.clicks ?? 0;
  const scrolls = comp.scroll_count ?? comp.scrolls ?? 0;
  const longestIdle = comp.longest_idle_seconds;

  return (
    <section className="report-section-root">
      <div className="report-section-header">
        <div className="report-section-title-group">
          <h2 className="report-section-title">Computer Activity</h2>
          <span className="report-section-subtitle">
            Local peripheral input counts without content or coordinate logging
          </span>
        </div>
      </div>

      <div className="report-card">
        <div className="report-metric-grid-5">
          <div className="metric-cell">
            <span className="metric-cell-label">Input Events</span>
            <span className="metric-cell-value">{inputEvents}</span>
            <span className="metric-cell-sub">Keyboard inputs detected</span>
          </div>
          <div className="metric-cell">
            <span className="metric-cell-label">Mouse Movements</span>
            <span className="metric-cell-value">{mouseMovements}</span>
            <span className="metric-cell-sub">Pointer displacement pulses</span>
          </div>
          <div className="metric-cell">
            <span className="metric-cell-label">Clicks</span>
            <span className="metric-cell-value">{clicks}</span>
            <span className="metric-cell-sub">Mouse click triggers</span>
          </div>
          <div className="metric-cell">
            <span className="metric-cell-label">Scroll Events</span>
            <span className="metric-cell-value">{scrolls}</span>
            <span className="metric-cell-sub">Wheel / trackpad scroll increments</span>
          </div>
          <div className="metric-cell">
            <span className="metric-cell-label">Longest Idle Period</span>
            <span className="metric-cell-value">{longestIdle != null ? formatDuration(longestIdle) : "—"}</span>
            <span className="metric-cell-sub">Continuous absence of input</span>
          </div>
        </div>

        <div className="activity-disclaimer-box mt-3">
          <svg className="report-info-icon" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z"
              clipRule="evenodd"
            />
          </svg>
          <span className="activity-disclaimer-text">
            Only activity counts are recorded. VisionGuard does not record typed content, passwords, screenshots, or mouse coordinates.
          </span>
        </div>
      </div>
    </section>
  );
};
