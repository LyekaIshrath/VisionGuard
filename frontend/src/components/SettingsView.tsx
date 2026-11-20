import React, { useState, useEffect } from "react";
import { useAlerts } from "../contexts/AlertContext";
import { useAuth } from "../contexts/AuthContext";
import { apiFetch } from "../services/apiClient";

interface SettingsViewProps {
  apiBase: string;
  onOpenPostureCalibration?: () => void;
  onOpenAlertnessCalibration?: () => void;
  canCalibratePosture: boolean;
  canCalibrateAlertness: boolean;
  postureCalibrated: boolean;
  alertnessCalibrated: boolean;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  apiBase,
  onOpenPostureCalibration,
  onOpenAlertnessCalibration,
  canCalibratePosture,
  canCalibrateAlertness,
  postureCalibrated,
  alertnessCalibrated,
}) => {
  const {
    browserPermission,
    browserNotificationsEnabled,
    voiceAlertsEnabled,
    isMuted,
    toggleMute,
    quietModeEnabled,
    setQuietMode,
    alertLanguage,
    setAlertLanguage,
    updatePreferences,
    requestBrowserNotifications,
    testBrowserNotification,
    testVoiceAlert,
  } = useAlerts();

  const { user } = useAuth();

  // Multi-Surface Notification Preferences State
  const [notifyPosture, setNotifyPosture] = useState<boolean>(true);
  const [notifyAlertness, setNotifyAlertness] = useState<boolean>(true);
  const [notifyExtendedAway, setNotifyExtendedAway] = useState<boolean>(true);
  const [notifySessionComplete, setNotifySessionComplete] = useState<boolean>(true);

  // Testing Feedback States
  const [testDesktopFeedback, setTestDesktopFeedback] = useState<string | null>(null);
  const [testVoiceFeedback, setTestVoiceFeedback] = useState<string | null>(null);

  // Load preferences on mount
  useEffect(() => {
    let isMounted = true;
    const fetchPrefs = async () => {
      try {
        const resp = await apiFetch(`${apiBase}/api/v1/user/preferences`);
        if (resp.ok) {
          const data = await resp.json();
          if (isMounted) {
            if (data.notify_posture !== undefined) setNotifyPosture(data.notify_posture);
            if (data.notify_alertness !== undefined) setNotifyAlertness(data.notify_alertness);
            if (data.notify_extended_away !== undefined) setNotifyExtendedAway(data.notify_extended_away);
            if (data.notify_session_complete !== undefined) setNotifySessionComplete(data.notify_session_complete);
          }
        }
      } catch {
        // Fallback to local defaults safely without breaking UI
      }
    };
    fetchPrefs();
    return () => {
      isMounted = false;
    };
  }, [apiBase]);

  const handleToggleEventFilter = async (
    key: "notify_posture" | "notify_alertness" | "notify_extended_away" | "notify_session_complete",
    val: boolean
  ) => {
    if (key === "notify_posture") setNotifyPosture(val);
    if (key === "notify_alertness") setNotifyAlertness(val);
    if (key === "notify_extended_away") setNotifyExtendedAway(val);
    if (key === "notify_session_complete") setNotifySessionComplete(val);
    await updatePreferences({ [key]: val });
  };

  // Test Handlers
  const handleTestDesktop = async () => {
    setTestDesktopFeedback(null);
    if (browserPermission !== "granted") {
      const granted = await requestBrowserNotifications();
      if (!granted) {
        setTestDesktopFeedback("Permission denied by browser.");
        return;
      }
    }
    const sent = testBrowserNotification();
    if (sent) {
      setTestDesktopFeedback("Desktop notification sent.");
      try {
        await apiFetch(`${apiBase}/api/v1/notifications/test-desktop`, { method: "POST" });
      } catch {}
    } else {
      setTestDesktopFeedback("Failed to display desktop alert.");
    }
    setTimeout(() => setTestDesktopFeedback(null), 4000);
  };

  const handleTestVoice = () => {
    setTestVoiceFeedback("Playing voice alert test...");
    testVoiceAlert();
    setTimeout(() => setTestVoiceFeedback(null), 4000);
  };

  return (
    <div className="settings-container" id="settings-section">
      <div className="settings-header">
        <h1 className="settings-title">SETTINGS</h1>
        <p className="settings-subtitle">
          Configure safety notifications, workstation audio, personalized baselines, and ergonomics.
        </p>
      </div>

      {/* 1. GENERAL / ACCOUNT / PROFILE */}
      <div className="dashboard-card settings-card">
        <div className="card-header">
          <div className="card-title-group">
            <h2 className="card-title">ACCOUNT &amp; PROFILE</h2>
            <span className="card-subtitle">Identity &amp; Cloud Synchronization</span>
          </div>
          {user ? (
            <span className="status-badge badge-good">
              <span className="badge-dot" />
              <span>AUTHENTICATED</span>
            </span>
          ) : (
            <span className="status-badge badge-unknown">
              <span className="badge-dot" />
              <span>GUEST / LOCAL USER</span>
            </span>
          )}
        </div>

        <div className="settings-card-body">
          <div className="account-status-row">
            <div>
              <span className="stat-label">Signed-in Account</span>
              <p className="account-email-display">
                {user?.email || "Guest / Local User"}
              </p>
              <p className="card-helper-text">
                {user ? `Display Name: ${user.display_name || "User"} • Status: Active` : "Sign in to securely sync ergonomic history and reports across workstations."}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 2. NOTIFICATIONS (DELIVERY SURFACES) */}
      <div className="dashboard-card settings-card">
        <div className="card-header">
          <div className="card-title-group">
            <h2 className="card-title">DELIVERY SURFACES</h2>
            <span className="card-subtitle">Multi-Channel Alert Dispatches</span>
          </div>
        </div>

        <div className="settings-card-body">
          <div className="settings-toggles-grid">
            {/* Desktop Notification Toggle */}
            <div className="settings-toggle-item">
              <div className="settings-toggle-info">
                <span className="settings-toggle-label">Desktop Notifications</span>
                <span className="settings-toggle-desc">Windows and browser native alert banners.</span>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={browserNotificationsEnabled}
                  onChange={(e) => updatePreferences({ browser_notifications_enabled: e.target.checked })}
                />
                <span className="slider round" />
              </label>
            </div>

            {/* Voice Alerts Toggle */}
            <div className="settings-toggle-item">
              <div className="settings-toggle-info">
                <span className="settings-toggle-label">Voice Alerts</span>
                <span className="settings-toggle-desc">Spoken audio alerts via workstation speakers.</span>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={voiceAlertsEnabled && !isMuted}
                  onChange={toggleMute}
                />
                <span className="slider round" />
              </label>
            </div>
          </div>
        </div>
      </div>

      {/* 3. EVENT FILTERS */}
      <div className="dashboard-card settings-card">
        <div className="card-header">
          <div className="card-title-group">
            <h2 className="card-title">EVENT FILTERS</h2>
            <span className="card-subtitle">Ergonomic &amp; Safety Alert Triggers</span>
          </div>
        </div>

        <div className="settings-card-body">
          <div className="settings-toggles-grid">
            <div className="settings-toggle-item">
              <div className="settings-toggle-info">
                <span className="settings-toggle-label">Posture Alerts</span>
                <span className="settings-toggle-desc">Sustained slouching or forward head tilt.</span>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={notifyPosture}
                  onChange={(e) => handleToggleEventFilter("notify_posture", e.target.checked)}
                />
                <span className="slider round" />
              </label>
            </div>

            <div className="settings-toggle-item">
              <div className="settings-toggle-info">
                <span className="settings-toggle-label">Alertness Alerts</span>
                <span className="settings-toggle-desc">Prolonged eye closure or drowsiness signals.</span>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={notifyAlertness}
                  onChange={(e) => handleToggleEventFilter("notify_alertness", e.target.checked)}
                />
                <span className="slider round" />
              </label>
            </div>

            <div className="settings-toggle-item">
              <div className="settings-toggle-info">
                <span className="settings-toggle-label">Extended Away</span>
                <span className="settings-toggle-desc">Notifications when absent beyond threshold.</span>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={notifyExtendedAway}
                  onChange={(e) => handleToggleEventFilter("notify_extended_away", e.target.checked)}
                />
                <span className="slider round" />
              </label>
            </div>

            <div className="settings-toggle-item">
              <div className="settings-toggle-info">
                <span className="settings-toggle-label">Session Complete</span>
                <span className="settings-toggle-desc">Session completion and summary report ready.</span>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={notifySessionComplete}
                  onChange={(e) => handleToggleEventFilter("notify_session_complete", e.target.checked)}
                />
                <span className="slider round" />
              </label>
            </div>
          </div>
        </div>
      </div>

      {/* 4. CHANNEL VERIFICATION TESTING */}
      <div className="dashboard-card settings-card">
        <div className="card-header">
          <div className="card-title-group">
            <h2 className="card-title">CHANNEL VERIFICATION TESTING</h2>
            <span className="card-subtitle">Test Delivery Paths to Confirm Reliability</span>
          </div>
        </div>

        <div className="settings-card-body">
          <div className="test-buttons-row">
            <div className="test-action-item">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleTestDesktop}
              >
                TEST DESKTOP
              </button>
              {testDesktopFeedback && (
                <p className="test-feedback-text info">{testDesktopFeedback}</p>
              )}
            </div>

            <div className="test-action-item">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleTestVoice}
              >
                TEST VOICE
              </button>
              {testVoiceFeedback && (
                <p className="test-feedback-text info">{testVoiceFeedback}</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 5. VOICE ALERT TUNING */}
      <div className="dashboard-card settings-card">
        <div className="card-header">
          <div className="card-title-group">
            <h2 className="card-title">VOICE ALERT TUNING</h2>
            <span className="card-subtitle">Speech Synthesis &amp; Quiet Mode Controls</span>
          </div>
        </div>

        <div className="settings-card-body">
          <div className="settings-toggles-grid">
            <div className="form-group">
              <label className="form-label">Spoken Alert Language</label>
              <select
                className="form-input"
                value={alertLanguage}
                onChange={(e) => setAlertLanguage(e.target.value as any)}
              >
                <option value="en">English (US/UK)</option>
                <option value="ta">Tamil (தமிழ்)</option>
                <option value="en+ta">Bilingual (English + Tamil)</option>
              </select>
            </div>

            <div className="settings-toggle-item">
              <div className="settings-toggle-info">
                <span className="settings-toggle-label">Master Quiet Mode</span>
                <span className="settings-toggle-desc">{quietModeEnabled ? "Muted (visual only alerts)" : "Active audio alerts"}</span>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={quietModeEnabled}
                  onChange={(e) => setQuietMode(e.target.checked)}
                />
                <span className="slider round" />
              </label>
            </div>
          </div>
        </div>
      </div>

      {/* 6. PERSONALIZATION / BASELINES */}
      <div className="dashboard-card settings-card">
        <div className="card-header">
          <div className="card-title-group">
            <h2 className="card-title">PERSONALIZATION &amp; CALIBRATION</h2>
            <span className="card-subtitle">Biomechanical Geometry &amp; Eye Baselines</span>
          </div>
        </div>

        <div className="settings-card-body">
          <div className="settings-toggles-grid">
            <div className="baseline-item-box">
              <div>
                <span className="settings-toggle-label">Posture Baseline</span>
                <p className="card-helper-text">
                  Status: <strong>{postureCalibrated ? "Calibrated" : "Engineering Default"}</strong>
                </p>
              </div>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={!canCalibratePosture || !onOpenPostureCalibration}
                onClick={onOpenPostureCalibration}
              >
                Personalize Posture Baseline
              </button>
            </div>

            <div className="baseline-item-box">
              <div>
                <span className="settings-toggle-label">Alertness Baseline</span>
                <p className="card-helper-text">
                  Status: <strong>{alertnessCalibrated ? "Calibrated" : "Engineering Default"}</strong>
                </p>
              </div>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={!canCalibrateAlertness || !onOpenAlertnessCalibration}
                onClick={onOpenAlertnessCalibration}
              >
                Personalize Eye Baseline
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 7. PRIVACY ARCHITECTURE */}
      <div className="dashboard-card settings-card privacy-callout-card">
        <div className="card-header">
          <div className="card-title-group">
            <h2 className="card-title">PRIVACY ARCHITECTURE</h2>
            <span className="card-subtitle">Zero-Image Cloud Transmission Guarantee</span>
          </div>
          <span className="privacy-badge">100% LOCAL PERCEPTION</span>
        </div>

        <div className="settings-card-body">
          <p className="privacy-callout-text">
            VisionGuard processes video frames exclusively on your local workstation via integrated computer vision.
            Raw webcam frames and face landmarks are NEVER uploaded, stored on servers, or shared with third parties.
          </p>
          <p className="privacy-callout-text" style={{ marginTop: "8px" }}>
            Only aggregated session metrics and ergonomic events are securely synced to MongoDB for personal history and reporting.
          </p>
        </div>
      </div>
    </div>
  );
};
