import React from "react";
import { formatDuration, formatPct } from "./ReportFormatters";
import { SessionDocument } from "./reportTypes";

interface PresenceAttentionProps {
  session: SessionDocument;
}

export const PresenceAttentionSection: React.FC<PresenceAttentionProps> = ({ session }) => {
  const dur = Math.max(1, session.duration_seconds || 1);
  const pres = session.presence_summary || {};
  const head = session.head_summary || {};
  const act = session.activity_summary || {};

  // Presence metrics
  const presentSec = pres.present_seconds ?? (session.duration_seconds - (pres.away_seconds || 0));
  const presentPct = pres.present_pct ?? (presentSec / dur) * 100;
  const awaySec = pres.away_seconds ?? 0;
  const awayPct = pres.away_pct ?? (awaySec / dur) * 100;
  const awayEpisodes = pres.away_episodes ?? (awaySec > 0 ? 1 : 0);
  const longestAway = pres.longest_away_seconds ?? (awayEpisodes === 1 ? awaySec : null);

  // Attention metrics (physical workstation orientation)
  const facingSec = head.facing_workstation_seconds ?? (presentSec - (head.attention_away_seconds ?? act.attention_away_seconds ?? 0));
  const facingPct = head.facing_workstation_pct ?? (facingSec / dur) * 100;
  const attentionAwaySec = head.attention_away_seconds ?? head.attention_away_duration_seconds ?? act.attention_away_seconds ?? 0;
  const attentionAwayPct = (attentionAwaySec / dur) * 100;
  const attentionAwayEpisodes = head.attention_away_episodes ?? (attentionAwaySec > 0 ? 1 : 0);

  return (
    <section className="report-section-root">
      <div className="report-section-header">
        <div className="report-section-title-group">
          <h2 className="report-section-title">Presence & Attention</h2>
          <span className="report-section-subtitle">
            Physical presence at desk separated from gaze and orientation signals
          </span>
        </div>
      </div>

      <div className="report-two-col-grid">
        {/* Presence Sub-panel */}
        <div className="report-card">
          <div className="card-header-badge">
            <span className="card-badge-dot bg-emerald" />
            <h3 className="card-subtitle">WORKSTATION OCCUPANCY</h3>
          </div>
          <div className="metric-row-group">
            <div className="metric-row">
              <span className="metric-row-label">Present at Desk</span>
              <div className="metric-row-data">
                <span className="metric-row-val text-emerald">{formatDuration(presentSec)}</span>
                <span className="metric-row-sub">({formatPct(presentPct)})</span>
              </div>
            </div>
            <div className="metric-row">
              <span className="metric-row-label">Away from Desk</span>
              <div className="metric-row-data">
                <span className="metric-row-val text-muted">{formatDuration(awaySec)}</span>
                <span className="metric-row-sub">({formatPct(awayPct)})</span>
              </div>
            </div>
            <div className="metric-row">
              <span className="metric-row-label">Away Episodes</span>
              <div className="metric-row-data">
                <span className="metric-row-val">{awayEpisodes}</span>
              </div>
            </div>
            <div className="metric-row">
              <span className="metric-row-label">Longest Away Period</span>
              <div className="metric-row-data">
                <span className="metric-row-val">{longestAway != null ? formatDuration(longestAway) : "—"}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Attention Sub-panel */}
        <div className="report-card">
          <div className="card-header-badge">
            <span className="card-badge-dot bg-amber" />
            <h3 className="card-subtitle">ATTENTION ORIENTATION</h3>
          </div>
          <div className="metric-row-group">
            <div className="metric-row">
              <span className="metric-row-label">Facing Workstation</span>
              <div className="metric-row-data">
                <span className="metric-row-val text-sky">{formatDuration(facingSec)}</span>
                <span className="metric-row-sub">({formatPct(facingPct)})</span>
              </div>
            </div>
            <div className="metric-row">
              <span className="metric-row-label">Attention Away</span>
              <div className="metric-row-data">
                <span className="metric-row-val text-amber">{formatDuration(attentionAwaySec)}</span>
                <span className="metric-row-sub">({formatPct(attentionAwayPct)})</span>
              </div>
            </div>
            <div className="metric-row">
              <span className="metric-row-label">Attention-Away Episodes</span>
              <div className="metric-row-data">
                <span className="metric-row-val">{attentionAwayEpisodes}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
