import React, { useEffect, useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import { WeeklyReport } from "../types";

export const ReportsView: React.FC = () => {
  const { session } = useAuth();
  const token = session?.access_token;

  const [weekOffset, setWeekOffset] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [weeklyReport, setWeeklyReport] = useState<WeeklyReport | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  const fetchReport = async () => {
    if (!token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      const res = await fetch(
        `/api/v1/reports/weekly?week_offset=${weekOffset}&tz=${encodeURIComponent(browserTz)}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) throw new Error("Failed to load weekly report");
      const data = await res.json();
      setWeeklyReport(data);
    } catch (err: any) {
      setError(err.message || "Failed to load report");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReport();
  }, [token, weekOffset]);

  const handleDownloadCsv = async (type: "sessions" | "risk-events") => {
    if (!token) return;
    setDownloading(type);
    try {
      const url = `/api/v1/reports/export/${type}/csv?days=30`;
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = downloadUrl;
      a.download = `visionguard_${type}_30d.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(downloadUrl);
    } catch (e) {
      console.error(e);
      alert("Failed to download CSV export.");
    } finally {
      setDownloading(null);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  if (!token) {
    return (
      <div className="reports-container not-logged-in">
        <div className="empty-cloud-prompt">
          <h3>Cloud Authentication Required</h3>
          <p>Sign in to view comprehensive weekly ergonomic reports and export session data.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="reports-view-container">
      {/* Top Header & Export Controls */}
      <div className="reports-top-bar no-print">
        <div>
          <h2 className="view-title">Ergonomic Reports & Exports</h2>
          <p className="view-subtitle">Official printable weekly wellness reviews and strictly whitelisted CSV data exports</p>
        </div>

        <div className="reports-actions">
          <button
            className="export-btn"
            disabled={downloading !== null}
            onClick={() => handleDownloadCsv("sessions")}
          >
            {downloading === "sessions" ? "Exporting..." : "📥 Export Sessions CSV (30d)"}
          </button>
          <button
            className="export-btn"
            disabled={downloading !== null}
            onClick={() => handleDownloadCsv("risk-events")}
          >
            {downloading === "risk-events" ? "Exporting..." : "📥 Export Risk Events CSV (30d)"}
          </button>
          <button className="print-btn" onClick={handlePrint}>
            🖨️ Save as PDF / Print
          </button>
        </div>
      </div>

      {/* Week Navigation */}
      <div className="week-nav-bar no-print">
        <button
          className="week-nav-btn"
          onClick={() => setWeekOffset((prev) => prev - 1)}
        >
          ← Previous Week
        </button>
        <span className="current-week-label">
          {weeklyReport ? `${weeklyReport.week_start} to ${weeklyReport.week_end}` : "Loading..."}
        </span>
        <button
          className="week-nav-btn"
          disabled={weekOffset >= 0}
          onClick={() => setWeekOffset((prev) => prev + 1)}
        >
          Next Week →
        </button>
      </div>

      {loading && (
        <div className="reports-loading">
          <div className="spinner"></div>
          <p>Compiling weekly ergonomic report...</p>
        </div>
      )}

      {error && <div className="reports-error">{error}</div>}

      {/* Printable Report Content */}
      {weeklyReport && !loading && (
        <div className="printable-report-sheet">
          <div className="report-header">
            <div className="report-brand">
              <span className="brand-logo">🛡️</span>
              <div>
                <h1 className="report-main-title">VisionGuard Personal Ergonomic Report</h1>
                <span className="report-date-range">
                  Week of {weeklyReport.week_start} through {weeklyReport.week_end} • Timezone: {weeklyReport.timezone}
                </span>
              </div>
            </div>
          </div>

          {/* Executive Summary Cards */}
          <div className="report-summary-cards">
            <div className="r-card">
              <span className="r-label">Monitored Exposure</span>
              <span className="r-val">{(weeklyReport.overview.total_monitored_seconds / 3600).toFixed(1)} hrs</span>
              <span className="r-sub">{weeklyReport.overview.total_sessions} active sessions</span>
            </div>
            <div className="r-card">
              <span className="r-label">Good Posture %</span>
              <span className="r-val">
                {weeklyReport.overview.good_posture_percentage !== null
                  ? `${weeklyReport.overview.good_posture_percentage}%`
                  : "N/A"}
              </span>
              <span className="r-sub">Valid observation time</span>
            </div>
            <div className="r-card">
              <span className="r-label">Posture Event Rate</span>
              <span className="r-val">
                {weeklyReport.overview.posture_events_per_valid_observation_hour !== null
                  ? `${weeklyReport.overview.posture_events_per_valid_observation_hour}/hr`
                  : "N/A"}
              </span>
              <span className="r-sub">Eligible cohort</span>
            </div>
            <div className="r-card">
              <span className="r-label">Total Risk Alerts</span>
              <span className="r-val">{weeklyReport.overview.total_risk_events}</span>
              <span className="r-sub">{weeklyReport.overview.total_interventions} interventions delivered</span>
            </div>
          </div>

          {/* Daily Breakdown Table */}
          <div className="report-section">
            <h3 className="r-section-title">Daily Observation Breakdown</h3>
            <table className="report-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Monitored Time</th>
                  <th>Good Posture %</th>
                  <th>Events / Valid Hr</th>
                  <th>Risk Events</th>
                  <th>Interventions</th>
                  <th>Telemetry Quality</th>
                </tr>
              </thead>
              <tbody>
                {weeklyReport.daily_trends.map((day) => {
                  const hrs = (day.total_monitored_seconds / 3600).toFixed(1);
                  return (
                    <tr key={day.date}>
                      <td className="font-semibold">{day.date}</td>
                      <td>{hrs} hrs</td>
                      <td>{day.good_posture_percentage !== null ? `${day.good_posture_percentage}%` : "--"}</td>
                      <td>{day.posture_events_per_valid_observation_hour !== null ? day.posture_events_per_valid_observation_hour : "--"}</td>
                      <td>{day.risk_event_count}</td>
                      <td>{day.intervention_count}</td>
                      <td>
                        <span className={`table-badge ${day.coverage.posture.data_quality.toLowerCase()}`}>
                          {day.coverage.posture.data_quality}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Time of Day Distribution */}
          <div className="report-section">
            <h3 className="r-section-title">Time of Day Exposure & Rate Analysis</h3>
            <div className="tod-table-grid">
              {weeklyReport.time_of_day_patterns.map((b) => (
                <div key={b.bucket} className="tod-report-box">
                  <span className="tod-box-title">{b.label}</span>
                  <div className="tod-box-stat">
                    <span className="stat-big">{(b.monitored_exposure_seconds / 3600).toFixed(1)}</span>
                    <span className="stat-small">hrs monitored</span>
                  </div>
                  <div className="tod-box-sub">
                    <span>{b.risk_event_count} events</span>
                    <span>•</span>
                    <span>{b.events_per_monitored_hour !== null ? `${b.events_per_monitored_hour} / hr` : "--"}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Key Insights */}
          {weeklyReport.insights.length > 0 && (
            <div className="report-section">
              <h3 className="r-section-title">Weekly Behavioral Observations</h3>
              <div className="report-insights-list">
                {weeklyReport.insights.map((ins) => (
                  <div key={ins.id} className="r-insight-card">
                    <h4 className="r-insight-title">{ins.title}</h4>
                    <p className="r-insight-desc">{ins.description}</p>
                    {ins.recommended_action && (
                      <p className="r-insight-action">Recommendation: {ins.recommended_action}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="report-footer">
            <p>Generated by VisionGuard • 100% Local CV Inference • Zero Raw Landmark or Video Transmission</p>
          </div>
        </div>
      )}
    </div>
  );
};
