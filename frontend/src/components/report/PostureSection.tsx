import React from "react";
import { formatDuration, formatPct } from "./ReportFormatters";
import { SessionDocument } from "./reportTypes";

interface PostureSectionProps {
  session: SessionDocument;
}

export const PostureSection: React.FC<PostureSectionProps> = ({ session }) => {
  const dur = Math.max(1, session.duration_seconds || 1);
  const post = session.posture_summary || {};

  const validPostureSec = post.valid_posture_seconds ?? session.valid_posture_seconds ?? (session.good_posture_seconds ?? 0);
  const unknownPostureSec = post.unknown_posture_seconds ?? Math.max(0, dur - validPostureSec);

  const validCoveragePct = post.valid_posture_seconds != null ? (validPostureSec / dur) * 100 : (dur > 0 ? (validPostureSec / dur) * 100 : 0);
  const unknownCoveragePct = (unknownPostureSec / dur) * 100;

  // Tracked Posture Distribution (Denominator = validPostureSec)
  const validDenom = Math.max(0, validPostureSec);
  const goodSec = post.good_posture_seconds ?? session.good_posture_seconds ?? 0;
  const slouchSec = post.slouching_seconds ?? 0;
  const forwardLeanSec = post.forward_lean_seconds ?? 0;
  const leftLeanSec = post.left_lean_seconds ?? 0;
  const rightLeanSec = post.right_lean_seconds ?? 0;

  const goodPct = post.good_pct ?? (validDenom > 0 ? (goodSec / validDenom) * 100 : 0);
  const slouchPct = post.slouching_pct ?? (validDenom > 0 ? (slouchSec / validDenom) * 100 : 0);
  const forwardLeanPct = post.forward_lean_pct ?? (validDenom > 0 ? (forwardLeanSec / validDenom) * 100 : 0);
  const leftLeanPct = post.left_lean_pct ?? (validDenom > 0 ? (leftLeanSec / validDenom) * 100 : 0);
  const rightLeanPct = post.right_lean_pct ?? (validDenom > 0 ? (rightLeanSec / validDenom) * 100 : 0);

  const postureStates = [
    { label: "Good Posture", sec: goodSec, pct: goodPct, color: "bg-emerald-500", text: "text-emerald" },
    { label: "Slouching", sec: slouchSec, pct: slouchPct, color: "bg-amber-500", text: "text-amber" },
    { label: "Forward Lean", sec: forwardLeanSec, pct: forwardLeanPct, color: "bg-orange-500", text: "text-orange" },
    { label: "Left Lean", sec: leftLeanSec, pct: leftLeanPct, color: "bg-blue-500", text: "text-blue" },
    { label: "Right Lean", sec: rightLeanSec, pct: rightLeanPct, color: "bg-purple-500", text: "text-purple" },
  ];

  if (!session.posture_summary && session.good_posture_seconds == null) {
    return (
      <section className="report-section-root">
        <div className="report-section-header">
          <h2 className="report-section-title">Posture & Ergonomics</h2>
        </div>
        <div className="report-card report-empty-state">
          Posture tracking data unavailable for this session.
        </div>
      </section>
    );
  }

  return (
    <section className="report-section-root">
      <div className="report-section-header">
        <div className="report-section-title-group">
          <h2 className="report-section-title">Posture & Ergonomics</h2>
          <span className="report-section-subtitle">
            Physical ergonomics with mathematically separate coverage and distribution denominators
          </span>
        </div>
      </div>

      <div className="report-two-col-grid">
        {/* Coverage Card */}
        <div className="report-card">
          <div className="card-header-badge">
            <span className="card-badge-dot bg-sky" />
            <h3 className="card-subtitle">POSTURE TRACKING COVERAGE</h3>
          </div>
          <span className="coverage-sublabel">Denominator: {formatDuration(dur)} total monitored duration</span>

          <div className="metric-row-group mt-3">
            <div className="metric-row">
              <span className="metric-row-label">Valid Posture Tracking</span>
              <div className="metric-row-data">
                <span className="metric-row-val text-sky">
                  {formatDuration(validPostureSec)} / {formatDuration(dur)}
                </span>
                <span className="metric-row-sub font-semibold">({formatPct(validCoveragePct)})</span>
              </div>
            </div>
            <div className="metric-row">
              <span className="metric-row-label">Tracking Unavailable</span>
              <div className="metric-row-data">
                <span className="metric-row-val text-muted">{formatDuration(unknownPostureSec)}</span>
                <span className="metric-row-sub">({formatPct(unknownCoveragePct)} of session)</span>
              </div>
            </div>
            <div className="metric-row">
              <span className="metric-row-label">Average Posture Score</span>
              <div className="metric-row-data">
                <span className="metric-row-val">
                  {session.average_posture_score != null ? `${session.average_posture_score.toFixed(1)} / 100` : "—"}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Tracked Posture Distribution Card */}
        <div className="report-card">
          <div className="card-header-badge">
            <span className="card-badge-dot bg-emerald" />
            <h3 className="card-subtitle">TRACKED POSTURE DISTRIBUTION</h3>
          </div>
          <span className="coverage-sublabel">
            Based strictly on {formatDuration(validPostureSec)} of valid posture tracking (equals 100%)
          </span>

          {validDenom <= 0 ? (
            <div className="p-3 text-xs text-slate-400">
              No valid posture frames were tracked during this session.
            </div>
          ) : (
            <>
              {/* Stacked Posture Bar */}
              <div className="activity-stacked-bar-wrapper mt-3">
                <div className="activity-stacked-bar">
                  {postureStates.map((ps, idx) =>
                    ps.pct > 0 ? (
                      <div
                        key={idx}
                        className={`activity-stacked-segment ${ps.color}`}
                        style={{ width: `${Math.max(0.5, ps.pct)}%` }}
                        title={`${ps.label}: ${formatDuration(ps.sec)} (${formatPct(ps.pct)})`}
                      />
                    ) : null
                  )}
                </div>
              </div>

              {/* Exact Distribution Items */}
              <div className="metric-row-group mt-3">
                {postureStates.map((ps, idx) => (
                  <div key={idx} className="metric-row">
                    <span className="metric-row-label">{ps.label}</span>
                    <div className="metric-row-data">
                      <span className={`metric-row-val ${ps.text}`}>{formatDuration(ps.sec)}</span>
                      <span className="metric-row-sub">({formatPct(ps.pct)})</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
};
