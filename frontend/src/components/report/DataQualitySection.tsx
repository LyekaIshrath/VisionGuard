import React from "react";
import { formatPct, formatDuration } from "./ReportFormatters";
import { SessionDocument } from "./reportTypes";

interface DataQualityProps {
  session: SessionDocument;
}

export const DataQualitySection: React.FC<DataQualityProps> = ({ session }) => {
  const dur = Math.max(1, session.duration_seconds || 1);
  const pres = session.presence_summary || {};
  const act = session.activity_summary || {};
  const post = session.posture_summary || {};
  const eyes = session.eye_summary || {};
  const scr = session.screen_summary || {};

  // Presence coverage: total present + away seconds / dur
  const presenceTotal = (pres.present_seconds ?? 0) + (pres.away_seconds ?? 0);
  const presenceCovPct = pres.present_seconds != null ? Math.min(100, (presenceTotal / dur) * 100) : null;

  // Activity coverage: sum of all 5 activity states / dur
  const activityTotal =
    (act.engaged_seconds ?? 0) +
    (act.observing_seconds ?? 0) +
    (act.attention_away_seconds ?? 0) +
    (act.away_seconds ?? 0) +
    (act.unknown_seconds ?? 0);
  const activityCovPct = act.engaged_seconds != null ? Math.min(100, (activityTotal / dur) * 100) : null;

  // Posture coverage
  const validPostureSec = post.valid_posture_seconds ?? session.valid_posture_seconds;
  const postureCovPct = validPostureSec != null ? (validPostureSec / dur) * 100 : null;

  // Eye tracking coverage
  const validEyeSec = eyes.valid_eye_tracking_seconds;
  const eyeCovPct = eyes.valid_eye_observation_pct ?? (validEyeSec != null ? (validEyeSec / dur) * 100 : null);

  // Screen signal coverage
  const screenChangingSec = scr.screen_active_seconds ?? scr.changing_seconds;
  const screenCovPct = scr.changing_pct ?? (screenChangingSec != null ? (screenChangingSec / dur) * 100 : null);

  const signals = [
    { label: "Presence Coverage", pct: presenceCovPct, note: "Workstation presence state accounted for" },
    { label: "Activity Coverage", pct: activityCovPct, note: "Classification duration across all 5 states" },
    { label: "Posture Coverage", pct: postureCovPct, note: validPostureSec != null ? `${formatDuration(validPostureSec)} valid tracking` : "Not available" },
    { label: "Eye Tracking Coverage", pct: eyeCovPct, note: validEyeSec != null ? `${formatDuration(validEyeSec)} valid tracking` : "Not available" },
    { label: "Screen Signal Coverage", pct: screenCovPct, note: screenChangingSec != null ? `${formatDuration(screenChangingSec)} screen signal observed` : "Not available" },
  ];

  return (
    <section className="report-section-root">
      <div className="report-section-header">
        <div className="report-section-title-group">
          <h2 className="report-section-title">Data Quality</h2>
          <span className="report-section-subtitle">
            Reliability and sensor telemetry coverage across the monitored duration
          </span>
        </div>
      </div>

      <div className="report-card">
        <div className="data-quality-grid">
          {signals.map((sig, idx) => (
            <div key={idx} className="quality-metric-row">
              <div className="quality-label-col">
                <span className="quality-label">{sig.label}</span>
                <span className="quality-note">{sig.note}</span>
              </div>
              <div className="quality-val-col">
                <span className="quality-val">
                  {sig.pct != null ? formatPct(sig.pct) : "—"}
                </span>
                {sig.pct != null ? (
                  <div className="quality-bar-track">
                    <div
                      className="quality-bar-fill"
                      style={{ width: `${Math.min(100, Math.max(0, sig.pct))}%` }}
                    />
                  </div>
                ) : (
                  <span className="quality-unavailable">Not available</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
