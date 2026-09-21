import React from "react";
import { formatDuration, formatPct } from "./ReportFormatters";
import { SessionDocument } from "./reportTypes";

interface ActivityDistributionProps {
  session: SessionDocument;
}

export const ActivityDistributionSection: React.FC<ActivityDistributionProps> = ({ session }) => {
  const dur = Math.max(1, session.duration_seconds || 1);
  const act = session.activity_summary || {};

  const engagedSec = act.engaged_seconds ?? 0;
  const observingSec = act.observing_seconds ?? 0;
  const attentionAwaySec = act.attention_away_seconds ?? 0;
  const awaySec = act.away_seconds ?? 0;
  const unknownSec = act.unknown_seconds ?? 0;

  // Compute exact percentage of total monitored time
  const engagedPct = act.engaged_pct ?? (engagedSec / dur) * 100;
  const observingPct = act.observing_pct ?? (observingSec / dur) * 100;
  const attentionAwayPct = act.attention_away_pct ?? (attentionAwaySec / dur) * 100;
  const awayPct = act.away_pct ?? (awaySec / dur) * 100;
  const unknownPct = act.unknown_pct ?? (unknownSec / dur) * 100;

  const states = [
    {
      key: "engaged",
      label: "Engaged",
      sec: engagedSec,
      pct: engagedPct,
      colorClass: "bg-state-engaged",
      textClass: "text-state-engaged",
      dotClass: "dot-state-engaged",
    },
    {
      key: "observing",
      label: "Observing",
      sec: observingSec,
      pct: observingPct,
      colorClass: "bg-state-observing",
      textClass: "text-state-observing",
      dotClass: "dot-state-observing",
    },
    {
      key: "attention_away",
      label: "Attention Away",
      sec: attentionAwaySec,
      pct: attentionAwayPct,
      colorClass: "bg-state-attention-away",
      textClass: "text-state-attention-away",
      dotClass: "dot-state-attention-away",
    },
    {
      key: "away",
      label: "Away",
      sec: awaySec,
      pct: awayPct,
      colorClass: "bg-state-away",
      textClass: "text-state-away",
      dotClass: "dot-state-away",
    },
    {
      key: "unknown",
      label: "Unknown",
      sec: unknownSec,
      pct: unknownPct,
      colorClass: "bg-state-unknown",
      textClass: "text-state-unknown",
      dotClass: "dot-state-unknown",
    },
  ];

  return (
    <section className="report-section-root">
      <div className="report-section-header">
        <div className="report-section-title-group">
          <h2 className="report-section-title">Work Activity</h2>
          <span className="report-section-subtitle">
            Observable workstation interaction & attention signals (Denominator: {formatDuration(session.duration_seconds)} monitored time)
          </span>
        </div>
      </div>

      <div className="report-card report-activity-card">
        {/* Horizontal Stacked Bar */}
        <div className="activity-stacked-bar-wrapper">
          <div className="activity-stacked-bar" role="progressbar" aria-label="Work Activity Distribution">
            {states.map((st) =>
              st.pct > 0 ? (
                <div
                  key={st.key}
                  className={`activity-stacked-segment ${st.colorClass}`}
                  style={{ width: `${Math.max(0.5, st.pct)}%` }}
                  title={`${st.label}: ${formatDuration(st.sec)} (${formatPct(st.pct)})`}
                />
              ) : null
            )}
          </div>
        </div>

        {/* States Breakdown Table / Grid */}
        <div className="activity-breakdown-grid">
          {states.map((st) => (
            <div key={st.key} className="activity-state-item">
              <div className="activity-state-header">
                <span className={`activity-dot ${st.dotClass}`} />
                <span className="activity-state-name">{st.label}</span>
              </div>
              <div className="activity-state-values">
                <span className={`activity-state-duration ${st.textClass}`}>
                  {formatDuration(st.sec)}
                </span>
                <span className="activity-state-pct">{formatPct(st.pct)}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Observational Notice Tooltip / Caption */}
        <div className="activity-disclaimer-box">
          <svg className="report-info-icon" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
              clipRule="evenodd"
            />
          </svg>
          <span className="activity-disclaimer-text">
            Activity states describe observable workstation interaction and attention signals. They are not productivity scores.
          </span>
        </div>
      </div>
    </section>
  );
};
