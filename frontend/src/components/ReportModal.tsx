import React from "react";
import { WorkSessionReport } from "./report/WorkSessionReport";
import { SessionDocument } from "./report/reportTypes";

export interface SessionReportData extends SessionDocument {}

interface ReportModalProps {
  report: any | null;
  onClose: () => void;
}

export const ReportModal: React.FC<ReportModalProps> = ({ report, onClose }) => {
  if (!report) return null;

  return (
    <WorkSessionReport
      session={report}
      sessionId={report.session_id || report.id}
      onClose={onClose}
    />
  );
};
