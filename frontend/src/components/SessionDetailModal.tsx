import { apiFetch } from "../services/apiClient";
﻿import React, { useEffect, useState } from "react";
import { SessionRecord, RiskEventRecord } from "../types";
import { useAuth } from "../contexts/AuthContext";

interface SessionDetailModalProps {
  session: SessionRecord | null;
  apiBase: string;
  onClose: () => void;
}

export const SessionDetailModal: React.FC<SessionDetailModalProps> = ({
  session,
  apiBase,
  onClose,
}) => {
  const { token } = useAuth();
  const [events, setEvents] = useState<RiskEventRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session || !token) return;

    const fetchEvents = async () => {
      setLoading(true);
      setError(null);
      try {
        const resp = await apiFetch(`${apiBase}/api/v1/sessions/${session.id}/events`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (resp.ok) {
          const data = await resp.json();
          setEvents(data);
        } else {
          setError("Failed to load events for this session.");
        }
      } catch (err: any) {
        setError(err.message || "Network error loading events.");
      } finally {
        setLoading(false);
      }
    };

    fetchEvents();
  }, [session, token, apiBase]);

  if (!session) return null;

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}m ${secs}s`;
  };

  return (
    <div className="modal-backdrop" onClick={onClose} aria-modal="true" role="dialog">
      <div className="modal-card session-detail-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-group">
            <h2 className="modal-title">Session Details</h2>
            <p className="modal-subtitle">
              Started {new Date(session.started_at).toLocaleString()} • {formatDuration(session.duration_seconds)}
            </p>
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        <div className="session-stats-grid">
          <div className="stat-card">
            <span className="stat-label">Posture Score</span>
            <span className="stat-value">{session.average_posture_score ?? "—"}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Alertness Score</span>
            <span className="stat-value">{session.average_alertness_score ?? "—"}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Good Posture Time</span>
            <span className="stat-value">{formatDuration(session.good_posture_seconds)}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Risk Events</span>
            <span className="stat-value">{session.risk_event_count}</span>
          </div>
        </div>

        <div className="events-section">
          <h3 className="section-heading">Associated Risk Events ({events.length})</h3>
          {loading ? (
            <div className="loading-indicator">Loading events...</div>
          ) : error ? (
            <div className="error-indicator">{error}</div>
          ) : events.length === 0 ? (
            <div className="empty-events-state">No risk events recorded during this session. Good job!</div>
          ) : (
            <div className="events-table-wrapper">
              <table className="events-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Category</th>
                    <th>Severity</th>
                    <th>Reason</th>
                    <th>Lifecycle</th>
                    <th>Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((evt) => (
                    <tr key={evt.id}>
                      <td>{new Date(evt.timestamp).toLocaleTimeString()}</td>
                      <td>
                        <span className={`badge badge-category badge-${evt.category.toLowerCase()}`}>
                          {evt.category}
                        </span>
                      </td>
                      <td>
                        <span className={`badge badge-severity badge-${evt.severity.toLowerCase()}`}>
                          {evt.severity}
                        </span>
                      </td>
                      <td>{evt.reason}</td>
                      <td>{evt.lifecycle}</td>
                      <td>{evt.duration_seconds ? `${evt.duration_seconds.toFixed(1)}s` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
