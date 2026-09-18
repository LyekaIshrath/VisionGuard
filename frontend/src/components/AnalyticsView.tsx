import React, { useEffect, useState } from "react";
import { AnalyticsSummary } from "../types";
import { useAuth } from "../contexts/AuthContext";

interface AnalyticsViewProps {
  apiBase: string;
  onOpenAuth: () => void;
}

export const AnalyticsView: React.FC<AnalyticsViewProps> = ({
  apiBase,
  onOpenAuth,
}) => {
  const { user, token } = useAuth();
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;

    const fetchAnalytics = async () => {
      setLoading(true);
      setError(null);
      try {
        const resp = await fetch(`${apiBase}/api/v1/analytics/summary`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (resp.ok) {
          const data: AnalyticsSummary = await resp.json();
          setSummary(data);
        } else {
          setError("Failed to load analytics from cloud.");
        }
      } catch (err: any) {
        setError(err.message || "Network error loading analytics.");
      } finally {
        setLoading(false);
      }
    };

    fetchAnalytics();
  }, [token, apiBase]);

  const formatHours = (seconds: number) => {
    const hours = (seconds / 3600).toFixed(1);
    return `${hours} hrs`;
  };

  if (!user || !token) {
    return (
      <div className="empty-history-view">
        <div className="empty-card">
          <div className="empty-icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M18 20V10" />
              <path d="M12 20V4" />
              <path d="M6 20v-6" />
            </svg>
          </div>
          <h2 className="empty-title">Sign in to View Ergonomic Analytics</h2>
          <p className="empty-subtitle">
            Historical analytics aggregate your posture adherence and alertness trends over time.
            Sign in with your VisionGuard account to access your personal wellness analytics.
          </p>
          <button className="btn btn-primary" onClick={onOpenAuth}>
            Sign In / Register
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="analytics-container">
      <div className="view-header">
        <div>
          <h2 className="view-title">Ergonomic &amp; Wellness Analytics</h2>
          <p className="view-subtitle">Aggregated trends and time-weighted metrics across your sessions</p>
        </div>
      </div>

      {error && <div className="auth-alert error">{error}</div>}

      {loading ? (
        <div className="loading-state">Aggregating historical analytics...</div>
      ) : !summary || summary.total_sessions === 0 ? (
        <div className="empty-card">
          <p className="empty-subtitle">No historical session data available yet. Complete monitoring sessions to see trends!</p>
        </div>
      ) : (
        <div className="analytics-grid">
          <div className="analytics-card highlight">
            <div className="analytics-card-header">
              <span className="card-label">Total Monitored Time</span>
              <span className="card-badge">{summary.total_sessions} Sessions</span>
            </div>
            <div className="card-big-value">{formatHours(summary.total_monitored_seconds)}</div>
            <p className="card-subtext">Active monitoring with local edge intelligence</p>
          </div>

          <div className="analytics-card">
            <div className="analytics-card-header">
              <span className="card-label">Good Posture Adherence</span>
            </div>
            <div className="card-big-value text-accent">{summary.good_posture_percentage}%</div>
            <p className="card-subtext">{formatHours(summary.total_good_posture_seconds)} in optimal posture</p>
          </div>

          <div className="analytics-card">
            <div className="analytics-card-header">
              <span className="card-label">Average Posture Score</span>
            </div>
            <div className="card-big-value">{summary.average_posture_score ?? "—"}</div>
            <p className="card-subtext">Time-weighted average score (0–100)</p>
          </div>

          <div className="analytics-card">
            <div className="analytics-card-header">
              <span className="card-label">Average Alertness Score</span>
            </div>
            <div className="card-big-value">{summary.average_alertness_score ?? "—"}</div>
            <p className="card-subtext">Time-weighted alertness metric</p>
          </div>

          <div className="analytics-card">
            <div className="analytics-card-header">
              <span className="card-label">Total Risk Events</span>
            </div>
            <div className="card-big-value text-warning">{summary.total_risk_events}</div>
            <p className="card-subtext">Temporal posture &amp; drowsiness alerts detected</p>
          </div>

          <div className="analytics-card">
            <div className="analytics-card-header">
              <span className="card-label">Calm Interventions</span>
            </div>
            <div className="card-big-value">{summary.total_interventions}</div>
            <p className="card-subtext">Actionable reminders presented to keep you safe</p>
          </div>
        </div>
      )}
    </div>
  );
};
