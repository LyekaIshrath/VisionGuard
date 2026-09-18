import React, { useEffect, useState } from "react";
import { SessionRecord } from "../types";
import { useAuth } from "../contexts/AuthContext";
import { SessionDetailModal } from "./SessionDetailModal";

interface SessionHistoryViewProps {
  apiBase: string;
  onOpenAuth: () => void;
}

export const SessionHistoryView: React.FC<SessionHistoryViewProps> = ({
  apiBase,
  onOpenAuth,
}) => {
  const { user, token } = useAuth();
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<SessionRecord | null>(null);

  const fetchSessions = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${apiBase}/api/v1/sessions?limit=50`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (resp.ok) {
        const data = await resp.json();
        setSessions(data);
      } else {
        setError("Unable to load monitoring sessions from cloud.");
      }
    } catch (err: any) {
      setError(err.message || "Failed to connect to backend.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (token) {
      fetchSessions();
    }
  }, [token]);

  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!token || !window.confirm("Are you sure you want to delete this session?")) return;

    try {
      const resp = await fetch(`${apiBase}/api/v1/sessions/${sessionId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (resp.ok) {
        setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      } else {
        alert("Failed to delete session.");
      }
    } catch (err) {
      alert("Error deleting session.");
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}m ${secs}s`;
  };

  if (!user || !token) {
    return (
      <div className="empty-history-view">
        <div className="empty-card">
          <div className="empty-icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <path d="M12 8v4" />
              <path d="M12 16h.01" />
            </svg>
          </div>
          <h2 className="empty-title">Sign in to View Session History</h2>
          <p className="empty-subtitle">
            VisionGuard isolates monitoring sessions per user using Supabase Row-Level Security (RLS).
            Sign in or create an account to view and synchronize your historical sessions.
          </p>
          <button className="btn btn-primary" onClick={onOpenAuth}>
            Sign In / Register
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="session-history-container">
      <div className="view-header">
        <div>
          <h2 className="view-title">Monitoring Sessions</h2>
          <p className="view-subtitle">Derived metrics &amp; timeline records stored with strict Row-Level Privacy</p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={fetchSessions} disabled={loading}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && <div className="auth-alert error">{error}</div>}

      {loading ? (
        <div className="loading-state">Loading your session history...</div>
      ) : sessions.length === 0 ? (
        <div className="empty-card">
          <p className="empty-subtitle">No monitoring sessions found yet. Start monitoring to record your first session!</p>
        </div>
      ) : (
        <div className="sessions-table-wrapper">
          <table className="sessions-table">
            <thead>
              <tr>
                <th>Date &amp; Time</th>
                <th>Duration</th>
                <th>Posture Score</th>
                <th>Alertness Score</th>
                <th>Good Posture %</th>
                <th>Risk Events</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => {
                const goodPct =
                  s.duration_seconds > 0
                    ? Math.round((s.good_posture_seconds / s.duration_seconds) * 100)
                    : 0;
                return (
                  <tr key={s.id} onClick={() => setSelectedSession(s)} className="session-row">
                    <td>{new Date(s.started_at).toLocaleString()}</td>
                    <td>{formatDuration(s.duration_seconds)}</td>
                    <td>
                      <span className="score-pill">
                        {s.average_posture_score !== null ? s.average_posture_score : "—"}
                      </span>
                    </td>
                    <td>
                      <span className="score-pill">
                        {s.average_alertness_score !== null ? s.average_alertness_score : "—"}
                      </span>
                    </td>
                    <td>{goodPct}%</td>
                    <td>{s.risk_event_count}</td>
                    <td>
                      <span className={`status-tag status-${s.status.toLowerCase()}`}>
                        {s.status}
                      </span>
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          className="btn-link"
                          onClick={() => setSelectedSession(s)}
                          title="View detailed risk events"
                        >
                          Details
                        </button>
                        <button
                          className="btn-link text-danger"
                          onClick={(e) => handleDeleteSession(s.id, e)}
                          title="Delete session"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selectedSession && (
        <SessionDetailModal
          session={selectedSession}
          apiBase={apiBase}
          onClose={() => setSelectedSession(null)}
        />
      )}
    </div>
  );
};
