import React from "react";
import { formatDuration, formatPct } from "./ReportFormatters";
import { SessionDocument } from "./reportTypes";

interface WellnessSummaryProps {
  session: SessionDocument;
}

export const WellnessSummary: React.FC<WellnessSummaryProps> = ({ session }) => {
  const dur = Math.max(1, session.duration_seconds || 1);
  const post = session.posture_summary || {};
  const eyes = session.eye_summary || {};
  const head = session.head_summary || {};

  const statements: string[] = [];

  // Posture statements
  const validPostureSec = post.valid_posture_seconds ?? session.valid_posture_seconds;
  if (validPostureSec != null) {
    const covPct = (validPostureSec / dur) * 100;
    statements.push(`Posture was tracked for ${formatPct(covPct)} of this session.`);

    if (validPostureSec > 0 && post.good_pct != null) {
      statements.push(`Good posture accounted for ${formatPct(post.good_pct)} of valid posture tracking time.`);
    }
  }

  // Eye tracking statements
  const validEyeSec = eyes.valid_eye_tracking_seconds;
  const blinkCount = eyes.blink_count ?? eyes.total_blinks;
  if (validEyeSec != null && validEyeSec > 0 && blinkCount != null) {
    statements.push(`${blinkCount} blinks were detected during ${formatDuration(validEyeSec)} of valid eye tracking.`);
  }

  // Attention statements
  const attentionAwayEpisodes = head.attention_away_episodes;
  if (attentionAwayEpisodes != null) {
    if (attentionAwayEpisodes === 1) {
      statements.push("One attention-away period was observed.");
    } else if (attentionAwayEpisodes > 1) {
      statements.push(`${attentionAwayEpisodes} attention-away periods were observed.`);
    } else {
      statements.push("No sustained attention-away periods were observed.");
    }
  }

  if (statements.length === 0) {
    statements.push(`Session telemetry was observed for ${formatDuration(dur)}.`);
  }

  return (
    <section className="report-section-root">
      <div className="report-section-header">
        <div className="report-section-title-group">
          <h2 className="report-section-title">Wellness Summary</h2>
          <span className="report-section-subtitle">
            Deterministic, neutral observational statements based strictly on telemetry
          </span>
        </div>
      </div>

      <div className="report-card wellness-card">
        <ul className="wellness-statement-list">
          {statements.map((stmt, idx) => (
            <li key={idx} className="wellness-statement-item">
              <span className="wellness-bullet" />
              <span className="wellness-text">{stmt}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
};
