import React from "react";
import { SessionRecord } from "../types";
import { useAuth } from "../contexts/AuthContext";
import { WorkSessionReport } from "./report/WorkSessionReport";

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

  if (!session) return null;

  return (
    <WorkSessionReport
      session={session as any}
      sessionId={session.id || (session as any).session_id}
      token={token}
      apiBase={apiBase}
      onClose={onClose}
    />
  );
};
