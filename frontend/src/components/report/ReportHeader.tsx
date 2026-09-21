import React, { useState } from "react";
import { formatSafeDate, formatTimeRange, formatDuration, formatSafeTime } from "./ReportFormatters";

interface ReportHeaderProps {
  sessionId: string;
  startedAt?: string;
  endedAt?: string;
  durationSeconds: number;
  status?: string;
}

export const ReportHeader: React.FC<ReportHeaderProps> = ({
  sessionId,
  startedAt,
  endedAt,
  durationSeconds,
  status = "COMPLETED",
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopyId = () => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(sessionId);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const normStatus = (status || "COMPLETED").toUpperCase();
  const badgeClass =
    normStatus === "COMPLETED"
      ? "report-badge-completed"
      : normStatus === "RUNNING"
      ? "report-badge-running"
      : "report-badge-interrupted";

  return (
    <header className="report-header-root">
      <div className="report-header-brand">
        <div className="report-brand-meta">
          <span className="report-brand-tag">VISIONGUARD INTELLIGENCE</span>
          <h1 className="report-brand-title">Work Session Intelligence Report</h1>
        </div>
        <div className="report-header-status-group">
          <span className={`report-status-badge ${badgeClass}`}>
            {normStatus}
          </span>
        </div>
      </div>

      <div className="report-header-meta-grid">
        <div className="report-meta-item">
          <span className="report-meta-label">Session Date</span>
          <span className="report-meta-value">{formatSafeDate(startedAt)}</span>
        </div>
        <div className="report-meta-item">
          <span className="report-meta-label">Time Window</span>
          <span className="report-meta-value">{formatTimeRange(startedAt, endedAt)}</span>
        </div>
        <div className="report-meta-item">
          <span className="report-meta-label">Monitored Duration</span>
          <span className="report-meta-value highlight">{formatDuration(durationSeconds)}</span>
        </div>
        <div className="report-meta-item">
          <span className="report-meta-label">Report Generated</span>
          <span className="report-meta-value">{formatSafeTime(new Date().toISOString(), true)}</span>
        </div>
      </div>

      <div className="report-session-id-row">
        <span className="report-session-id-label">Session Reference:</span>
        <span className="report-session-id-mono">{sessionId}</span>
        <button
          type="button"
          onClick={handleCopyId}
          className="report-btn-copy"
          title="Copy full session UUID to clipboard"
          aria-label="Copy session ID"
        >
          {copied ? "Copied!" : "Copy Session ID"}
        </button>
      </div>
    </header>
  );
};
