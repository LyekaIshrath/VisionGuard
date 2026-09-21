import React, { useEffect, useState } from "react";
import { CloudStatusInfo, CloudSyncStatus } from "../types";

interface CloudSyncPillProps {
  apiBase: string;
}

export const CloudSyncPill: React.FC<CloudSyncPillProps> = ({ apiBase }) => {
  const [statusInfo, setStatusInfo] = useState<CloudStatusInfo>({
    status: "DISABLED",
    configured: false,
    cloud_session_id: null,
    local_session_id: null,
    message: "Checking cloud status...",
  });

  const fetchStatus = async () => {
    try {
      const resp = await fetch(`${apiBase}/api/v1/cloud/status`);
      if (resp.ok) {
        const data: CloudStatusInfo = await resp.json();
        setStatusInfo(data);
      }
    } catch {
      setStatusInfo((prev) => ({
        ...prev,
        status: "OFFLINE",
        message: "Backend cloud service unreachable.",
      }));
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [apiBase]);

  const getPillConfig = (status: CloudSyncStatus) => {
    switch (status) {
      case "SYNCED":
        return { dotClass: "cloud-dot synced", text: "Data: Synced", badgeClass: "badge-synced" };
      case "SYNCING":
        return { dotClass: "cloud-dot syncing", text: "Syncing...", badgeClass: "badge-syncing" };
      case "OFFLINE":
        return { dotClass: "cloud-dot offline", text: "Data: Offline", badgeClass: "badge-offline" };
      case "ERROR":
        return { dotClass: "cloud-dot error", text: "Data: Error", badgeClass: "badge-error" };
      case "DISABLED":
      default:
        return { dotClass: "cloud-dot disabled", text: "Data: Local Only", badgeClass: "badge-disabled" };
    }
  };

  const config = getPillConfig(statusInfo.status);

  return (
    <div
      className={`cloud-sync-pill ${config.badgeClass}`}
      title={statusInfo.message}
      aria-label={`Data status: ${statusInfo.status}`}
    >
      <span className={config.dotClass} />
      <span className="cloud-sync-text">{config.text}</span>
    </div>
  );
};
