import { apiFetch } from "../services/apiClient";
import React, { useEffect, useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import {
  AnalyticsOverview,
  DailyTrendItem,
  TimeOfDayBucket,
  Insight,
  PersonalGoal,
  GoalType
} from "../types";
import { TrendLineChart } from "./TrendLineChart";
import { TimeOfDayChart } from "./TimeOfDayChart";
import { InsightsCard } from "./InsightsCard";
import { PersonalGoalsCard } from "./PersonalGoalsCard";

interface AnalyticsViewProps {
  apiBase?: string;
  onOpenAuth?: () => void;
}

export const AnalyticsView: React.FC<AnalyticsViewProps> = ({ apiBase = "", onOpenAuth }) => {
  const { session } = useAuth();
  const token = session?.access_token;

  const [days, setDays] = useState<number>(14);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [trends, setTrends] = useState<DailyTrendItem[]>([]);
  const [timeOfDay, setTimeOfDay] = useState<TimeOfDayBucket[]>([]);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [goals, setGoals] = useState<PersonalGoal[]>([]);

  const fetchAnalytics = async () => {
    if (!token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      const headers = { Authorization: `Bearer ${token}` };

      const [ovRes, trRes, todRes, inRes, gRes] = await Promise.all([
        apiFetch(`${apiBase}/api/v1/analytics/overview?days=${days}&tz=${encodeURIComponent(browserTz)}`, { headers }),
        apiFetch(`${apiBase}/api/v1/analytics/trends?days=${days}&tz=${encodeURIComponent(browserTz)}`, { headers }),
        apiFetch(`${apiBase}/api/v1/analytics/patterns?days=${days}&tz=${encodeURIComponent(browserTz)}`, { headers }),
        apiFetch(`${apiBase}/api/v1/analytics/insights?days=${days}&tz=${encodeURIComponent(browserTz)}`, { headers }),
        apiFetch(`${apiBase}/api/v1/goals?tz=${encodeURIComponent(browserTz)}`, { headers }),
      ]);

      if (!ovRes.ok) throw new Error("Failed to load analytics overview");
      const ovData = await ovRes.json();
      setOverview(ovData);

      if (trRes.ok) setTrends(await trRes.json());
      if (todRes.ok) setTimeOfDay(await todRes.json());
      if (inRes.ok) setInsights(await inRes.json());
      if (gRes.ok) setGoals(await gRes.json());
    } catch (err: any) {
      setError(err.message || "Failed to load personal intelligence");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, [token, days, apiBase]);

  const handleSaveGoal = async (goalType: GoalType, target: number) => {
    if (!token) return;
    const res = await apiFetch(`${apiBase}/api/v1/goals`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ goal_type: goalType, target_value: target }),
    });
    if (!res.ok) throw new Error("Failed to update goal");
    await fetchAnalytics();
  };

  const handleDeleteGoal = async (goalId: string) => {
    if (!token) return;
    await apiFetch(`${apiBase}/api/v1/goals/${goalId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    await fetchAnalytics();
  };

  if (!token) {
    return (
      <div className="analytics-container not-logged-in">
        <div className="empty-cloud-prompt">
          <h3>Cloud Authentication Required</h3>
          <p>Sign in to sync your sessions and access personal ergonomic intelligence and trends.</p>
          {onOpenAuth && (
            <button className="auth-btn-prompt" onClick={onOpenAuth}>
              Sign In to Cloud
            </button>
          )}
        </div>
      </div>
    );
  }

  if (loading && !overview) {
    return (
      <div className="analytics-loading">
        <div className="spinner"></div>
        <p>Computing personal ergonomics intelligence...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="analytics-error">
        <p>{error}</p>
        <button className="retry-btn" onClick={fetchAnalytics}>
          Retry
        </button>
      </div>
    );
  }

  const monitoredHours = overview ? (overview.total_monitored_seconds / 3600).toFixed(1) : "0.0";
  const pQuality = overview?.coverage.posture.data_quality;
  const aQuality = overview?.coverage.alertness.data_quality;

  return (
    <div className="personal-intelligence-view">
      {/* Top Header */}
      <div className="view-header-row">
        <div>
          <h2 className="view-title">Personal Intelligence & Analytics</h2>
          <p className="view-subtitle">
            Long-term ergonomic trends, valid-observation rates, and deterministic wellness insights
          </p>
        </div>

        {/* Days range selector */}
        <div className="range-selector">
          {[7, 14, 30].map((d) => (
            <button
              key={d}
              className={`range-btn ${days === d ? "active" : ""}`}
              onClick={() => setDays(d)}
            >
              {d} Days
            </button>
          ))}
        </div>
      </div>

      {/* Coverage Status Bar */}
      {overview && (
        <div className="coverage-status-banner">
          <span className="coverage-label">Data Telemetry Quality:</span>
          <span className={`quality-badge ${pQuality?.toLowerCase()}`}>
            Posture: {pQuality} ({overview.coverage.posture.sessions_with_known_exposure}/{overview.coverage.sessions_total} sessions)
          </span>
          <span className={`quality-badge ${aQuality?.toLowerCase()}`}>
            Alertness: {aQuality} ({overview.coverage.alertness.sessions_with_known_exposure}/{overview.coverage.sessions_total} sessions)
          </span>
          {pQuality === "PARTIAL" && (
            <span className="coverage-notice-text">
              ℹ️ Rates strictly exclude sessions where observation duration was unrecorded.
            </span>
          )}
        </div>
      )}

      {/* Overview Stat Cards */}
      {overview && (
        <div className="overview-stats-grid">
          <div className="stat-card">
            <span className="stat-label">Total Monitored</span>
            <div className="stat-val-group">
              <span className="stat-value">{monitoredHours}</span>
              <span className="stat-unit">hours</span>
            </div>
            <span className="stat-hint">{overview.total_sessions} total sessions</span>
          </div>

          <div className="stat-card">
            <span className="stat-label">Good Posture Ratio</span>
            <div className="stat-val-group">
              <span className="stat-value">
                {overview.good_posture_percentage !== null ? `${overview.good_posture_percentage}%` : "--"}
              </span>
            </div>
            <span className="stat-hint">of verified observation exposure</span>
          </div>

          <div className="stat-card">
            <span className="stat-label">Posture Risk Rate</span>
            <div className="stat-val-group">
              <span className="stat-value">
                {overview.posture_events_per_valid_observation_hour !== null
                  ? overview.posture_events_per_valid_observation_hour
                  : "--"}
              </span>
              <span className="stat-unit">events / hr</span>
            </div>
            <span className="stat-hint">matched cohort rate</span>
          </div>

          <div className="stat-card">
            <span className="stat-label">Alertness Risk Rate</span>
            <div className="stat-val-group">
              <span className="stat-value">
                {overview.alertness_events_per_valid_observation_hour !== null
                  ? overview.alertness_events_per_valid_observation_hour
                  : "--"}
              </span>
              <span className="stat-unit">events / hr</span>
            </div>
            <span className="stat-hint">matched cohort rate</span>
          </div>
        </div>
      )}

      {/* Deterministic Insights */}
      {insights.length > 0 && <InsightsCard insights={insights} />}

      {/* Daily Trends Chart */}
      <div className="chart-section-card">
        <div className="chart-header">
          <h3 className="section-title">Daily Ergonomic Trends</h3>
          <span className="section-subtitle">Good posture adherence and risk event frequency over the last {days} days</span>
        </div>
        <TrendLineChart data={trends} />
      </div>

      {/* Time of Day Distribution */}
      <div className="chart-section-card">
        <div className="chart-header">
          <h3 className="section-title">Time of Day Vulnerability Patterns</h3>
          <span className="section-subtitle">Active monitored exposure hours and risk frequency across morning, afternoon, evening, and night</span>
        </div>
        <TimeOfDayChart data={timeOfDay} />
      </div>

      {/* Personal Goals */}
      <PersonalGoalsCard
        goals={goals}
        onSaveGoal={handleSaveGoal}
        onDeleteGoal={handleDeleteGoal}
      />
    </div>
  );
};
