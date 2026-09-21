import React from "react";
import { SessionDocument } from "./reportTypes";

interface ReportToolbarProps {
  session: SessionDocument;
  onClose: () => void;
}

export const ReportToolbar: React.FC<ReportToolbarProps> = ({ session, onClose }) => {
  const handlePrint = () => {
    window.print();
  };

  const handleExportJSON = () => {
    const jsonStr = JSON.stringify(session, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `visionguard-session-${(session.session_id || session.id || "report").slice(0, 8)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleExportCSV = () => {
    // Generate clean CSV of this session's metrics
    const rows = [
      ["Metric", "Value", "Unit / Notes"],
      ["Session ID", session.session_id || session.id || "", ""],
      ["Status", session.status || "COMPLETED", ""],
      ["Started At", session.started_at || "", "ISO Timestamp"],
      ["Ended At", session.ended_at || "", "ISO Timestamp"],
      ["Duration Seconds", String(session.duration_seconds || 0), "Seconds"],
      ["Present Seconds", String(session.presence_summary?.present_seconds ?? ""), "Seconds"],
      ["Away Seconds", String(session.presence_summary?.away_seconds ?? ""), "Seconds"],
      ["Away Episodes", String(session.presence_summary?.away_episodes ?? ""), "Count"],
      ["Engaged Seconds", String(session.activity_summary?.engaged_seconds ?? ""), "Seconds"],
      ["Observing Seconds", String(session.activity_summary?.observing_seconds ?? ""), "Seconds"],
      ["Attention Away Seconds", String(session.activity_summary?.attention_away_seconds ?? ""), "Seconds"],
      ["Activity Away Seconds", String(session.activity_summary?.away_seconds ?? ""), "Seconds"],
      ["Unknown Seconds", String(session.activity_summary?.unknown_seconds ?? ""), "Seconds"],
      ["Valid Posture Seconds", String(session.posture_summary?.valid_posture_seconds ?? ""), "Seconds"],
      ["Good Posture Seconds", String(session.posture_summary?.good_posture_seconds ?? ""), "Seconds"],
      ["Slouch Seconds", String(session.posture_summary?.slouching_seconds ?? ""), "Seconds"],
      ["Total Blinks", String(session.eye_summary?.blink_count ?? session.eye_summary?.total_blinks ?? ""), "Count"],
      ["Blink Rate (/min)", String(session.eye_summary?.blink_rate_per_min ?? session.eye_summary?.blink_rate ?? ""), "per min"],
      ["Valid Eye Tracking Seconds", String(session.eye_summary?.valid_eye_tracking_seconds ?? ""), "Seconds"],
      ["Input Events", String(session.computer_summary?.keyboard_events ?? session.computer_summary?.keystrokes ?? ""), "Count"],
      ["Mouse Movements", String(session.computer_summary?.mouse_movements ?? session.computer_summary?.mouse_moves ?? ""), "Count"],
      ["Mouse Clicks", String(session.computer_summary?.mouse_clicks ?? session.computer_summary?.clicks ?? ""), "Count"],
      ["Scroll Events", String(session.computer_summary?.scroll_count ?? session.computer_summary?.scrolls ?? ""), "Count"],
    ];

    const csvContent = rows
      .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
      .join("\r\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `visionguard-session-${(session.session_id || session.id || "report").slice(0, 8)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="report-toolbar print-hide">
      <button
        type="button"
        onClick={onClose}
        className="report-toolbar-back-btn"
        aria-label="Return to sessions list"
      >
        <svg className="report-back-arrow" viewBox="0 0 20 20" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z"
            clipRule="evenodd"
          />
        </svg>
        <span>Sessions</span>
      </button>

      <span className="report-toolbar-title">Work Session Report</span>

      <div className="report-toolbar-actions">
        <button
          type="button"
          onClick={handlePrint}
          className="report-btn-action"
          title="Print or save as PDF"
        >
          <svg className="w-4 h-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
          </svg>
          <span>Print</span>
        </button>

        <button
          type="button"
          onClick={handleExportCSV}
          className="report-btn-action"
          title="Export session metrics to CSV"
        >
          <svg className="w-4 h-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <span>Export CSV</span>
        </button>

        <button
          type="button"
          onClick={handleExportJSON}
          className="report-btn-action"
          title="Export raw session telemetry JSON"
        >
          <span>JSON</span>
        </button>

        <button
          type="button"
          onClick={onClose}
          className="report-btn-close"
          aria-label="Close report"
        >
          &times;
        </button>
      </div>
    </div>
  );
};
