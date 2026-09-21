import React from "react";
import { formatDuration, formatPct } from "./ReportFormatters";
import { SessionDocument } from "./reportTypes";

interface ExecutiveSummaryCardsProps {
  session: SessionDocument;
}

export const ExecutiveSummaryCards: React.FC<ExecutiveSummaryCardsProps> = ({ session }) => {
  const dur = session.duration_seconds || 0;
  const pres = session.presence_summary || {};
  const act = session.activity_summary || {};
  const eyes = session.eye_summary || {};

  // Presence time and percentage
  const presentSec = pres.present_seconds ?? (dur > 0 ? dur - (pres.away_seconds || 0) : 0);
  const presentPct = pres.present_pct ?? (dur > 0 ? (presentSec / dur) * 100 : 0);

  // Engaged time and percentage
  const engagedSec = act.engaged_seconds ?? 0;
  const engagedPct = act.engaged_pct ?? (dur > 0 ? (engagedSec / dur) * 100 : 0);

  // Attention Away time and percentage
  const attentionAwaySec = act.attention_away_seconds ?? 0;
  const attentionAwayPct = act.attention_away_pct ?? (dur > 0 ? (attentionAwaySec / dur) * 100 : 0);

  // Away time and percentage
  const awaySec = pres.away_seconds ?? act.away_seconds ?? 0;
  const awayPct = pres.away_pct ?? act.away_pct ?? (dur > 0 ? (awaySec / dur) * 100 : 0);

  // Blinks & Rate
  const blinkCount = eyes.blink_count ?? eyes.total_blinks ?? 0;
  const blinkRate = eyes.blink_rate_per_min ?? eyes.blink_rate;
  const validEyeSec = eyes.valid_eye_tracking_seconds;

  let blinkSubtext = "Eye tracking observed";
  if (validEyeSec != null && validEyeSec > 0 && blinkRate != null) {
    blinkSubtext = `${blinkRate}/min over ${formatDuration(validEyeSec)} valid tracking`;
  } else if (validEyeSec != null && validEyeSec === 0) {
    blinkSubtext = "Insufficient valid eye-tracking time";
  }

  return (
    <section className="report-section-root">
      <div className="report-section-header">
        <h2 className="report-section-title">Executive Session Summary</h2>
        <span className="report-section-subtitle">Core observable telemetry at a glance</span>
      </div>

      <div className="report-exec-grid">
        {/* Monitored Time */}
        <div className="report-card exec-card">
          <span className="exec-card-label">MONITORED TIME</span>
          <span className="exec-card-value">{formatDuration(dur)}</span>
          <span className="exec-card-subtext">Complete session duration</span>
        </div>

        {/* Presence */}
        <div className="report-card exec-card">
          <span className="exec-card-label">PRESENCE</span>
          <span className="exec-card-value">{formatDuration(presentSec)}</span>
          <span className="exec-card-subtext">{formatPct(presentPct)} of monitored time</span>
        </div>

        {/* Engaged Time */}
        <div className="report-card exec-card">
          <span className="exec-card-label">ENGAGED TIME</span>
          <span className="exec-card-value text-emerald">{formatDuration(engagedSec)}</span>
          <span className="exec-card-subtext">{formatPct(engagedPct)} of monitored time</span>
        </div>

        {/* Attention Away */}
        <div className="report-card exec-card">
          <span className="exec-card-label">ATTENTION AWAY</span>
          <span className="exec-card-value text-amber">{formatDuration(attentionAwaySec)}</span>
          <span className="exec-card-subtext">{formatPct(attentionAwayPct)} of monitored time</span>
        </div>

        {/* Away Time */}
        <div className="report-card exec-card">
          <span className="exec-card-label">AWAY TIME</span>
          <span className="exec-card-value text-muted">{formatDuration(awaySec)}</span>
          <span className="exec-card-subtext">{formatPct(awayPct)} of monitored time</span>
        </div>

        {/* Blink Count */}
        <div className="report-card exec-card">
          <span className="exec-card-label">BLINK COUNT</span>
          <span className="exec-card-value text-sky">{blinkCount}</span>
          <span className="exec-card-subtext">{blinkSubtext}</span>
        </div>
      </div>
    </section>
  );
};
