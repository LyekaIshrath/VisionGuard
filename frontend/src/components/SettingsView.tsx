import React, { useState, useEffect } from "react";
import { useAlerts } from "../contexts/AlertContext";
import { useAuth } from "../contexts/AuthContext";
import { apiFetch } from "../services/apiClient";

interface SettingsViewProps {
  apiBase?: string;
  onOpenPostureCalibration?: () => void;
  onOpenAlertnessCalibration?: () => void;
  canCalibratePosture?: boolean;
  canCalibrateAlertness?: boolean;
  postureCalibrated?: boolean;
  alertnessCalibrated?: boolean;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  apiBase = "",
  onOpenPostureCalibration,
  onOpenAlertnessCalibration,
  canCalibratePosture = true,
  canCalibrateAlertness = true,
  postureCalibrated = false,
  alertnessCalibrated = false,
}) => {
  const {
    isMuted,
    quietModeEnabled,
    voiceAlertsEnabled,
    alertLanguage,
    setAlertLanguage,
    browserNotificationsEnabled,
    browserPermission,
    toggleMute,
    setQuietMode,
    updatePreferences,
    requestBrowserNotifications,
    testBrowserNotification,
    testVoiceAlert,
  } = useAlerts();

  const { user, startPhoneChange, verifyPhoneChange, refreshUser } = useAuth();

  // Multi-Surface Notification Preferences State
  const [smsAlertsEnabled, setSmsAlertsEnabled] = useState<boolean>(true);
  const [notifyPosture, setNotifyPosture] = useState<boolean>(true);
  const [notifyAlertness, setNotifyAlertness] = useState<boolean>(true);
  const [notifyExtendedAway, setNotifyExtendedAway] = useState<boolean>(true);
  const [notifySessionComplete, setNotifySessionComplete] = useState<boolean>(true);

  // Testing Feedback States
  const [testDesktopFeedback, setTestDesktopFeedback] = useState<string | null>(null);
  const [testSmsFeedback, setTestSmsFeedback] = useState<string | null>(null);
  const [testVoiceFeedback, setTestVoiceFeedback] = useState<string | null>(null);
  const [isSendingTestSms, setIsSendingTestSms] = useState<boolean>(false);

  // Phone Change Modal / Flow State
  const [isChangingPhone, setIsChangingPhone] = useState<boolean>(false);
  const [changeStep, setChangeStep] = useState<"INPUT" | "OTP">("INPUT");
  const [newPhoneNumber, setNewPhoneNumber] = useState<string>("");
  const [otpCode, setOtpCode] = useState<string>("");
  const [phoneChangeError, setPhoneChangeError] = useState<string | null>(null);
  const [phoneChangeSuccess, setPhoneChangeSuccess] = useState<string | null>(null);
  const [phoneChangeLoading, setPhoneChangeLoading] = useState<boolean>(false);

  // Load preferences on mount
  useEffect(() => {
    let isMounted = true;
    const fetchPrefs = async () => {
      try {
        const resp = await apiFetch(`${apiBase}/api/v1/user/preferences`);
        if (resp.ok) {
          const data = await resp.json();
          if (isMounted) {
            if (data.sms_alerts_enabled !== undefined) setSmsAlertsEnabled(data.sms_alerts_enabled);
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

  const handleToggleSms = async (enabled: boolean) => {
    setSmsAlertsEnabled(enabled);
    await updatePreferences({ sms_alerts_enabled: enabled });
  };

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

  const handleTestSms = async () => {
    setTestSmsFeedback(null);
    setIsSendingTestSms(true);
    try {
      const resp = await apiFetch(`${apiBase}/api/v1/notifications/test-sms`, { method: "POST" });
      const data = await resp.json();
      if (resp.ok) {
        setTestSmsFeedback(`SMS dispatched to ${data.delivery_summary?.recipient || "your verified phone"}.`);
      } else {
        setTestSmsFeedback(data.detail || "Failed to send test SMS.");
      }
    } catch (err: any) {
      setTestSmsFeedback(err.message || "Network error sending test SMS.");
    } finally {
      setIsSendingTestSms(false);
      setTimeout(() => setTestSmsFeedback(null), 6000);
    }
  };

  const handleTestVoice = () => {
    setTestVoiceFeedback("Playing voice alert test...");
    testVoiceAlert();
    setTimeout(() => setTestVoiceFeedback(null), 4000);
  };

  // Phone Change Handlers
  const handleStartPhoneChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPhoneChangeError(null);
    setPhoneChangeSuccess(null);

    if (!newPhoneNumber.trim()) {
      setPhoneChangeError("Please enter your new mobile number.");
      return;
    }

    setPhoneChangeLoading(true);
    try {
      const { error } = await startPhoneChange(newPhoneNumber.trim());
      if (error) {
        setPhoneChangeError(error.message);
      } else {
        setPhoneChangeSuccess("Verification code sent to new mobile number.");
        setChangeStep("OTP");
      }
    } finally {
      setPhoneChangeLoading(false);
    }
  };

  const handleVerifyPhoneChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPhoneChangeError(null);
    setPhoneChangeSuccess(null);

    if (!otpCode.trim() || otpCode.trim().length < 4) {
      setPhoneChangeError("Please enter the verification code.");
      return;
    }

    setPhoneChangeLoading(true);
    try {
      const { error } = await verifyPhoneChange(newPhoneNumber.trim(), otpCode.trim());
      if (error) {
        setPhoneChangeError(error.message);
      } else {
        setPhoneChangeSuccess("Phone number successfully updated and verified!");
        await refreshUser();
        setTimeout(() => {
          setIsChangingPhone(false);
          setChangeStep("INPUT");
          setNewPhoneNumber("");
          setOtpCode("");
          setPhoneChangeSuccess(null);
        }, 1200);
      }
    } finally {
      setPhoneChangeLoading(false);
    }
  };

  return (
    <div className="settings-container" id="settings-section">
      <div className="settings-header">
        <h1 className="settings-title">SETTINGS</h1>
        <p className="settings-subtitle">
          Configure safety notifications, workstation audio, verified channels, and personalized baselines.
        </p>
      </div>

      {/* 1. GENERAL / ACCOUNT / VERIFIED PHONE */}
      <div className="dashboard-card settings-card">
        <div className="card-header">
          <div className="card-title-group">
            <h2 className="card-title">ACCOUNT &amp; VERIFIED PHONE</h2>
            <span className="card-subtitle">Identity &amp; Multi-Surface SMS Gateway</span>
          </div>
          {user ? (
            user.phone_verified ? (
              <span className="status-badge badge-good">
                <span className="badge-dot" />
                <span>PHONE VERIFIED</span>
              </span>
            ) : (
              <span className="status-badge badge-warning">
                <span className="badge-dot" />
                <span>UNVERIFIED PHONE</span>
              </span>
            )
          ) : (
            <span className="status-badge badge-unknown">
              <span className="badge-dot" />
              <span>GUEST / LOCAL USER</span>
            </span>
          )}
        </div>

        <div className="settings-card-body">
          <div className="phone-status-row">
            <div>
              <span className="stat-label">Linked Mobile Number</span>
              <p className="phone-number-display">
                {user?.phone_masked || (user?.phone_number ? user.phone_number : "No mobile number linked")}
              </p>
              <p className="card-helper-text">
                Critical posture, alertness, and session summary alerts are delivered directly to this phone via SMS.
              </p>
            </div>

            {user ? (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setIsChangingPhone(!isChangingPhone);
                  setChangeStep("INPUT");
                  setPhoneChangeError(null);
                  setPhoneChangeSuccess(null);
                }}
              >
                {isChangingPhone ? "Cancel" : "Change Phone Number"}
              </button>
            ) : (
              <p className="signin-notice-text">
                Sign in to link a verified mobile number for remote SMS alerts.
              </p>
            )}
          </div>

          {/* Inline Phone Change Form */}
          {isChangingPhone && (
            <div className="phone-change-box">
              {phoneChangeError && (
                <div className="auth-banner auth-banner-error">
                  <span>{phoneChangeError}</span>
                </div>
              )}
              {phoneChangeSuccess && (
                <div className="auth-banner auth-banner-success">
                  <span>{phoneChangeSuccess}</span>
                </div>
              )}

              {changeStep === "INPUT" ? (
                <form onSubmit={handleStartPhoneChange} className="phone-form">
                  <div className="form-group" style={{ flex: "1 1 240px" }}>
                    <label className="form-label">New Mobile Number (E.164 format, e.g. +919876543210)</label>
                    <input
                      type="tel"
                      className="form-input"
                      placeholder="+919876543210"
                      value={newPhoneNumber}
                      onChange={(e) => setNewPhoneNumber(e.target.value)}
                      disabled={phoneChangeLoading}
                      required
                    />
                  </div>
                  <button type="submit" className="btn btn-primary btn-sm" disabled={phoneChangeLoading}>
                    {phoneChangeLoading ? "Sending OTP..." : "Send Verification Code"}
                  </button>
                </form>
              ) : (
                <form onSubmit={handleVerifyPhoneChange} className="phone-form">
                  <div className="form-group" style={{ flex: "1 1 200px" }}>
                    <label className="form-label">Enter 6-Digit OTP Code</label>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="123456"
                      value={otpCode}
                      onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                      disabled={phoneChangeLoading}
                      autoFocus
                      required
                    />
                  </div>
                  <button type="submit" className="btn btn-primary btn-sm" disabled={phoneChangeLoading || otpCode.length < 4}>
                    {phoneChangeLoading ? "Verifying..." : "Verify & Save Phone"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setChangeStep("INPUT")}
                    disabled={phoneChangeLoading}
                  >
                    Back
                  </button>
                </form>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 2. NOTIFICATIONS (DELIVERY CHANNELS) */}
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

            {/* SMS Alerts Toggle */}
            <div className="settings-toggle-item">
              <div className="settings-toggle-info">
                <span className="settings-toggle-label">SMS Alerts</span>
                <span className="settings-toggle-desc">Direct text messages to verified mobile phone.</span>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={smsAlertsEnabled}
                  onChange={(e) => handleToggleSms(e.target.checked)}
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
                onClick={handleTestSms}
                disabled={isSendingTestSms || !user?.phone_verified}
              >
                {isSendingTestSms ? "SENDING SMS..." : "TEST SMS"}
              </button>
              {testSmsFeedback && (
                <p className={`test-feedback-text ${testSmsFeedback.includes("dispatched") ? "success" : "danger"}`}>
                  {testSmsFeedback}
                </p>
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
