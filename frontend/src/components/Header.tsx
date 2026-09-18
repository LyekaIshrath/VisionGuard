import React from "react";
import { MonitoringState } from "../types";
import { CloudSyncPill } from "./CloudSyncPill";
import { useAuth } from "../contexts/AuthContext";
import { useAlerts } from "../contexts/AlertContext";

interface HeaderProps {
  monitoringState: MonitoringState;
  cameraState: string;
  isStarting: boolean;
  onToggleMonitoring: () => void;
  onToggleSidebar: () => void;
  apiBase: string;
  onOpenAuth: () => void;
  onOpenStatus?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  monitoringState,
  cameraState,
  isStarting,
  onToggleMonitoring,
  onToggleSidebar,
  apiBase,
  onOpenAuth,
  onOpenStatus,
}) => {
  const { user, signOut } = useAuth();
  const {
    isMuted,
    toggleMute,
    quietModeEnabled,
    browserPermission,
    requestBrowserNotifications,
  } = useAlerts();

  const isRunning = monitoringState === "RUNNING";
  const isError = monitoringState === "CAMERA_ERROR" || cameraState === "CAMERA_ERROR";
  const isNoFrames = monitoringState === "NO_FRAMES" || cameraState === "NO_FRAMES";

  const getStatusDisplay = () => {
    if (isRunning && cameraState === "READY") {
      return { dot: "status-dot live", text: "LIVE Monitoring", label: "Active" };
    }
    if (cameraState === "READY") {
      return { dot: "status-dot ready", text: "Camera Ready", label: "Ready" };
    }
    if (isNoFrames) {
      return { dot: "status-dot warning", text: "No Frames", label: "Warning" };
    }
    if (isError) {
      return { dot: "status-dot error", text: "Camera Error", label: "Error" };
    }
    return { dot: "status-dot stopped", text: "Monitoring Stopped", label: "Standby" };
  };

  const status = getStatusDisplay();

  return (
    <header className="app-header" id="overview">
      <div className="header-left">
        <button className="mobile-menu-btn" onClick={onToggleSidebar} aria-label="Open Navigation Menu">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        <div className="header-title-group">
          <h1 className="header-title">VisionGuard</h1>
          <p className="header-subtitle">Human Safety &amp; Wellness Intelligence</p>
        </div>
      </div>

      <div className="header-right">
        {/* Quiet Mode Indicator */}
        {quietModeEnabled && (
          <div className="system-pill" style={{ borderColor: "#f59e0b", color: "#f59e0b" }} title="Quiet Mode is active: voice alerts and notifications silenced">
            <span style={{ fontSize: "11px", fontWeight: 600 }}>QUIET MODE</span>
          </div>
        )}

        {/* Audio Mute Quick Toggle */}
        <button
          className={`btn btn-sm ${isMuted ? "btn-danger" : "btn-secondary"}`}
          onClick={toggleMute}
          title={isMuted ? "Unmute Voice Alerts" : "Mute Voice Alerts (immediately cancels active speech)"}
          style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
        >
          {isMuted ? (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="1" y1="1" x2="23" y2="23" />
                <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6" />
                <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
              <span>Muted</span>
            </>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" />
              </svg>
              <span>Voice</span>
            </>
          )}
        </button>

        {/* Cloud Sync Status Pill */}
        <CloudSyncPill apiBase={apiBase} />

        <div className="system-pill clickable" aria-live="polite" onClick={onOpenStatus} title="Click to view System Status Center" style={{ cursor: "pointer" }}>
          <span className={status.dot} />
          <span className="system-pill-text">{status.text}</span>
        </div>

        <div className="notification-control">
          {browserPermission === "granted" ? (
            <span className="notif-status-badge" title="Browser notifications enabled">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
              <span>Alerts ON</span>
            </span>
          ) : browserPermission === "denied" ? (
            <span className="notif-status-badge blocked" title="Notifications blocked in browser settings">
              <span>Alerts Blocked</span>
            </span>
          ) : (
            <button
              className="btn btn-secondary btn-sm notif-btn"
              onClick={requestBrowserNotifications}
              title="Click to enable desktop browser alerts for high-risk interventions"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
              <span>Enable Alerts</span>
            </button>
          )}
        </div>

        {/* User Auth Controls */}
        <div className="auth-header-control">
          {user ? (
            <div className="user-profile-badge">
              <span className="user-avatar-circle">{user.email ? user.email[0].toUpperCase() : "U"}</span>
              <span className="user-email-text" title={user.email || "Authenticated User"}>
                {user.email || "Authenticated"}
              </span>
              <button className="btn-signout" onClick={signOut} title="Sign Out">
                Sign Out
              </button>
            </div>
          ) : (
            <button className="btn btn-secondary btn-sm auth-btn" onClick={onOpenAuth}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              <span>Sign In</span>
            </button>
          )}
        </div>

        <div className="cta-control">
          <button
            className={`btn ${isRunning || isNoFrames ? "btn-danger" : "btn-primary"} header-cta`}
            disabled={isStarting}
            onClick={onToggleMonitoring}
          >
            {isStarting ? (
              <>
                <span className="btn-spinner" aria-hidden="true" />
                <span>Updating...</span>
              </>
            ) : isRunning || isNoFrames ? (
              <>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="6" width="12" height="12" rx="2" />
                </svg>
                <span>Stop Monitoring</span>
              </>
            ) : (
              <>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
                <span>Start Monitoring</span>
              </>
            )}
          </button>
        </div>
      </div>
    </header>
  );
};
