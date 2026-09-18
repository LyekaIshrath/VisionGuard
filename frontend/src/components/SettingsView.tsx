import React from "react";
import { useAlerts } from "../contexts/AlertContext";

export const SettingsView: React.FC = () => {
  const {
    isMuted,
    quietModeEnabled,
    voiceAlertsEnabled,
    voiceVolume,
    voiceRate,
    voicePitch,
    selectedVoice,
    alertLanguage,
    setAlertLanguage,
    browserNotificationsEnabled,
    browserPermission,
    availableVoices,
    toggleMute,
    setQuietMode,
    updatePreferences,
    requestBrowserNotifications,
    testVoiceAlert,
  } = useAlerts();

  return (
    <div className="view-container settings-view" id="settings-section">
      <div className="view-header">
        <div>
          <h2 className="view-title">Alert &amp; Voice Settings</h2>
          <p className="view-subtitle">
            Configure how VisionGuard warns you about posture and alertness risks.
          </p>
        </div>
      </div>

      <div className="settings-grid">
        {/* Quick Controls Card */}
        <section className="dashboard-card settings-card" aria-labelledby="quick-controls-heading">
          <div className="card-header">
            <h3 id="quick-controls-heading" className="card-title">Quick Controls</h3>
          </div>
          <div className="settings-options-list">
            <div className="setting-item">
              <div className="setting-info">
                <span className="setting-label">Audio Mute</span>
                <span className="setting-desc">
                  Immediately silence current and pending voice alerts without altering your permanent preferences.
                </span>
              </div>
              <button
                className={`btn btn-sm ${isMuted ? "btn-danger" : "btn-secondary"}`}
                onClick={toggleMute}
              >
                {isMuted ? "Unmute Voice" : "Mute Voice"}
              </button>
            </div>

            <div className="setting-item">
              <div className="setting-info">
                <span className="setting-label">Ergonomic Timezone</span>
                <span className="setting-desc">
                  Used to split daily metrics and time-of-day exposure. Defaults to your browser detection when unsaved.
                </span>
              </div>
              <div className="tz-select-group">
                <span className="badge badge-secondary">{Intl.DateTimeFormat().resolvedOptions().timeZone}</span>
              </div>
            </div>

            <div className="setting-item">
              <div className="setting-info">
                <span className="setting-label">Quiet Mode</span>
                <span className="setting-desc">
                  Suppresses all spoken alerts and desktop notifications while continuing active monitoring and in-app indicators.
                </span>
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
        </section>

        {/* Voice Alerts Card */}
        <section className="dashboard-card settings-card" aria-labelledby="voice-alerts-heading">
          <div className="card-header">
            <h3 id="voice-alerts-heading" className="card-title">Local Voice Alerts</h3>
          </div>
          <div className="settings-options-list">
            <div className="setting-item">
              <div className="setting-info">
                <span className="setting-label">Enable Voice Alerts</span>
                <span className="setting-desc">
                  Speak calm, deterministic guidance when moderate or high risks are detected.
                </span>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={voiceAlertsEnabled}
                  onChange={(e) => updatePreferences({ voice_alerts_enabled: e.target.checked })}
                />
                <span className="slider round" />
              </label>
            </div>

            <div className="setting-item-block">
              <label htmlFor="alert-language-select" className="setting-label">Alert Language</label>
              <p className="setting-description">
                Choose the spoken alert language. VisionGuard uses natural studio-quality pre-rendered audio for English and தமிழ்.
              </p>
              <select
                id="alert-language-select"
                className="form-select"
                value={alertLanguage}
                onChange={(e) => setAlertLanguage(e.target.value as "en" | "ta" | "en+ta")}
                disabled={!voiceAlertsEnabled || quietModeEnabled}
              >
                <option value="en">English (Natural Studio Audio)</option>
                <option value="ta">தமிழ் (இயற்கையான குரல்)</option>
                <option value="en+ta">English + தமிழ் (Bilingual Sequential)</option>
              </select>
            </div>

            <div className="setting-item-block">
              <span className="setting-label">Spoken Voice Capability</span>
              <p className="setting-description">
                {availableVoices.some((v) => v.lang.toLowerCase().startsWith("ta"))
                  ? "Local Tamil speech synthesizer detected. Natural pre-rendered studio audio is prioritized for crisp alerts."
                  : "No native Tamil system synthesizer detected. VisionGuard automatically delivers natural pre-rendered Tamil audio assets without English voice fallback."}
              </p>
            </div>

            <div className="setting-item-block">
              <label htmlFor="voice-select" className="setting-label">Synthesizer Voice (Dynamic English)</label>
              <select
                id="voice-select"
                className="form-select"
                value={selectedVoice || ""}
                onChange={(e) => updatePreferences({ selected_voice: e.target.value || null })}
                disabled={!voiceAlertsEnabled || quietModeEnabled}
              >
                <option value="">Default System Voice</option>
                {availableVoices.map((v) => (
                  <option key={v.name} value={v.name}>
                    {v.name} ({v.lang})
                  </option>
                ))}
              </select>
            </div>

            {/* Volume Slider */}
            <div className="setting-item-block">
              <div className="slider-header">
                <label htmlFor="volume-range" className="setting-label">Voice Volume</label>
                <span className="slider-value">{Math.round(voiceVolume * 100)}%</span>
              </div>
              <input
                id="volume-range"
                type="range"
                min="0.0"
                max="1.0"
                step="0.05"
                value={voiceVolume}
                onChange={(e) => updatePreferences({ voice_volume: parseFloat(e.target.value) })}
                disabled={!voiceAlertsEnabled || quietModeEnabled}
                className="slider-input"
              />
            </div>

            {/* Rate Slider */}
            <div className="setting-item-block">
              <div className="slider-header">
                <label htmlFor="rate-range" className="setting-label">Speech Speed (Rate)</label>
                <span className="slider-value">{voiceRate.toFixed(2)}x</span>
              </div>
              <input
                id="rate-range"
                type="range"
                min="0.5"
                max="2.0"
                step="0.05"
                value={voiceRate}
                onChange={(e) => updatePreferences({ voice_rate: parseFloat(e.target.value) })}
                disabled={!voiceAlertsEnabled || quietModeEnabled}
                className="slider-input"
              />
            </div>

            {/* Pitch Slider */}
            <div className="setting-item-block">
              <div className="slider-header">
                <label htmlFor="pitch-range" className="setting-label">Voice Pitch</label>
                <span className="slider-value">{voicePitch.toFixed(2)}</span>
              </div>
              <input
                id="pitch-range"
                type="range"
                min="0.5"
                max="2.0"
                step="0.05"
                value={voicePitch}
                onChange={(e) => updatePreferences({ voice_pitch: parseFloat(e.target.value) })}
                disabled={!voiceAlertsEnabled || quietModeEnabled}
                className="slider-input"
              />
            </div>

            <div className="setting-actions">
              <button
                className="btn btn-secondary btn-sm"
                onClick={testVoiceAlert}
                disabled={!voiceAlertsEnabled || quietModeEnabled || isMuted}
              >
                Test Voice Alert
              </button>
            </div>
          </div>
        </section>

        {/* Desktop Notifications Card */}
        <section className="dashboard-card settings-card" aria-labelledby="desktop-notif-heading">
          <div className="card-header">
            <h3 id="desktop-notif-heading" className="card-title">Browser &amp; Desktop Notifications</h3>
          </div>
          <div className="settings-options-list">
            <div className="setting-item">
              <div className="setting-info">
                <span className="setting-label">Notification Permission</span>
                <span className="setting-desc">
                  Current browser status: <strong style={{ textTransform: "capitalize" }}>{browserPermission}</strong>
                </span>
              </div>
              {browserPermission === "granted" ? (
                <span className="badge badge-success">Allowed</span>
              ) : browserPermission === "denied" ? (
                <span className="badge badge-danger">Blocked in Browser</span>
              ) : (
                <button
                  className="btn btn-primary btn-sm"
                  onClick={requestBrowserNotifications}
                >
                  Enable Desktop Notifications
                </button>
              )}
            </div>

            {browserPermission === "granted" && (
              <div className="setting-item">
                <div className="setting-info">
                  <span className="setting-label">Send Notifications</span>
                  <span className="setting-desc">
                    Display native OS banners for sustained posture or alertness risks (30s cooldown).
                  </span>
                </div>
                <label className="toggle-switch">
                  <input
                    type="checkbox"
                    checked={browserNotificationsEnabled}
                    onChange={(e) =>
                      updatePreferences({ browser_notifications_enabled: e.target.checked })
                    }
                  />
                  <span className="slider round" />
                </label>
              </div>
            )}
          </div>
        </section>

        {/* Privacy Card */}
        <section className="dashboard-card settings-card privacy-callout-card" aria-labelledby="privacy-heading">
          <div className="card-header">
            <h3 id="privacy-heading" className="card-title">Privacy &amp; Audio Architecture</h3>
          </div>
          <p className="privacy-callout-text">
            VisionGuard uses the browser/OS Speech Synthesis interface and does not send alert audio or text to a VisionGuard cloud TTS service.
          </p>
          <p className="privacy-callout-text" style={{ marginTop: "8px" }}>
            VisionGuard never requests microphone permission and never records audio. All computer vision processing remains local on your device.
          </p>
        </section>
      </div>
    </div>
  );
};
