import React, { useEffect, useState } from "react";
import "./report.css";
import { SessionDocument } from "./reportTypes";
import { ReportToolbar } from "./ReportToolbar";
import { ReportHeader } from "./ReportHeader";
import { ExecutiveSummaryCards } from "./ExecutiveSummaryCards";
import { ActivityDistributionSection } from "./ActivityDistributionSection";
import { PresenceAttentionSection } from "./PresenceAttentionSection";
import { ComputerActivitySection } from "./ComputerActivitySection";
import { ScreenActivitySection } from "./ScreenActivitySection";
import { PostureSection } from "./PostureSection";
import { EyeAlertnessSection } from "./EyeAlertnessSection";
import { SessionActivityBar } from "./SessionActivityBar";
import { SessionTimeline } from "./SessionTimeline";
import { WellnessSummary } from "./WellnessSummary";
import { DataQualitySection } from "./DataQualitySection";
import { PrivacyPanel } from "./PrivacyPanel";
import { apiFetch } from "../../services/apiClient";
import { useAuth } from "../../contexts/AuthContext";

export interface WorkSessionReportProps {
  session?: SessionDocument | null;
  sessionId?: string | null;
  token?: string | null;
  apiBase?: string;
  onClose: () => void;
}

export const WorkSessionReport: React.FC<WorkSessionReportProps> = ({
  session: initialSession,
  sessionId,
  token,
  apiBase = "",
  onClose,
}) => {
  const { token: authContextToken } = useAuth();
  const effectiveToken = token || authContextToken || (typeof window !== "undefined" ? localStorage.getItem("visionguard_token") : null);
  const [session, setSession] = useState<SessionDocument | null>(initialSession || null);
  const [loading, setLoading] = useState<boolean>(!initialSession && !!sessionId);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // If we have an initial session, ensure it is set
    if (initialSession) {
      setSession(initialSession);
      // If activity_intervals or timeline are not on initialSession, but we have sessionId and token, attempt enrichment
      const sid = initialSession.session_id || initialSession.id;
      if (sid && effectiveToken && (!initialSession.activity_intervals || !initialSession.timeline)) {
        apiFetch(`${apiBase}/api/v1/sessions/${sid}`, {
          headers: { Authorization: `Bearer ${effectiveToken}` },
        })
          .then((res) => (res.ok ? res.json() : null))
          .then((data) => {
            if (data) {
              setSession((prev) => ({
                ...(prev || {}),
                ...data,
                activity_intervals: data.activity_intervals || prev?.activity_intervals,
                timeline: data.timeline || prev?.timeline,
              } as SessionDocument));
            }
          })
          .catch(() => {});
      }
      return;
    }

    // If no initial session but sessionId provided, fetch it
    if (sessionId) {
      setLoading(true);
      setError(null);
      apiFetch(`${apiBase}/api/v1/sessions/${sessionId}`, {
        headers: effectiveToken ? { Authorization: `Bearer ${effectiveToken}` } : {},
      })
        .then(async (res) => {
          if (res.status === 404) {
            setError("Session report not found.");
            return;
          }
          if (!res.ok) {
            setError("Unable to load session report.");
            return;
          }
          const data = await res.json();
          setSession(data);
        })
        .catch((err) => {
          setError(err.message || "Network error loading session report.");
        })
        .finally(() => {
          setLoading(false);
        });
    }
  }, [initialSession, sessionId, token, apiBase]);

  if (loading) {
    return (
      <div className="work-session-report-modal" onClick={onClose} role="dialog" aria-modal="true">
        <div className="report-modal-dialog" onClick={(e) => e.stopPropagation()}>
          <div className="report-toolbar">
            <span className="report-toolbar-title">Work Session Report</span>
            <button type="button" onClick={onClose} className="report-btn-close">&times;</button>
          </div>
          <div className="report-content-container">
            <div className="report-empty-state">Loading session report…</div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="work-session-report-modal" onClick={onClose} role="dialog" aria-modal="true">
        <div className="report-modal-dialog" onClick={(e) => e.stopPropagation()}>
          <div className="report-toolbar">
            <span className="report-toolbar-title">Work Session Report</span>
            <button type="button" onClick={onClose} className="report-btn-close">&times;</button>
          </div>
          <div className="report-content-container">
            <div className="report-empty-state">{error || "Session report not found."}</div>
          </div>
        </div>
      </div>
    );
  }

  const sid = session.session_id || session.id || "session";
  const events = session.timeline || session.timeline_events || session.events || [];
  const intervals = session.activity_intervals || [];

  return (
    <div className="work-session-report-modal" onClick={onClose} role="dialog" aria-modal="true">
      <div className="report-modal-dialog" onClick={(e) => e.stopPropagation()}>
        {/* Navigation Toolbar */}
        <ReportToolbar session={session} onClose={onClose} />

        {/* Scrollable Report Content */}
        <div className="report-content-container">
          {/* 1. Header */}
          <ReportHeader
            sessionId={sid}
            startedAt={session.started_at}
            endedAt={session.ended_at}
            durationSeconds={session.duration_seconds || 0}
            status={session.status}
          />

          {/* 2. Executive Summary */}
          <ExecutiveSummaryCards session={session} />

          {/* 10. Session Activity Continuous Bar */}
          <SessionActivityBar
            intervals={intervals}
            totalDurationSeconds={session.duration_seconds || 0}
          />

          {/* 3. Work Activity Distribution */}
          <ActivityDistributionSection session={session} />

          {/* 4. Presence & Attention */}
          <PresenceAttentionSection session={session} />

          {/* 7. Posture & Ergonomics (Fixed Denominators) */}
          <PostureSection session={session} />

          {/* 8. Eye & Alertness Signals */}
          <EyeAlertnessSection session={session} />

          {/* 5. Computer Activity */}
          <ComputerActivitySection session={session} />

          {/* 6. Screen Activity */}
          <ScreenActivitySection session={session} />

          {/* 9. Session Timeline */}
          <SessionTimeline
            timeline={events}
            startedAt={session.started_at}
            endedAt={session.ended_at}
          />

          {/* 11. Wellness Summary */}
          <WellnessSummary session={session} />

          {/* 12. Data Quality */}
          <DataQualitySection session={session} />

          {/* 13. Privacy Panel */}
          <PrivacyPanel />
        </div>
      </div>
    </div>
  );
};
