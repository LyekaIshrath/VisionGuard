import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { Intervention, UserPreferences } from "../types";
import { speechProvider } from "../services/voiceAlertProvider";
import { voiceQueue } from "../services/voiceQueue";
import { notificationService } from "../services/browserNotifications";
import { apiFetch } from "../services/apiClient";
import { useAuth } from "./AuthContext";

interface AlertContextValue {
  isMuted: boolean;
  quietModeEnabled: boolean;
  voiceAlertsEnabled: boolean;
  voiceVolume: number;
  voiceRate: number;
  voicePitch: number;
  selectedVoice: string | null;
  alertLanguage: "en" | "ta" | "en+ta";
  browserNotificationsEnabled: boolean;
  browserPermission: NotificationPermission;
  availableVoices: SpeechSynthesisVoice[];
  acknowledgedAlertIds: Set<string>;
  toggleMute: () => void;
  setQuietMode: (enabled: boolean) => Promise<void>;
  setAlertLanguage: (lang: "en" | "ta" | "en+ta") => Promise<void>;
  updatePreferences: (updates: Partial<UserPreferences>) => Promise<void>;
  requestBrowserNotifications: () => Promise<boolean>;
  acknowledgeAlert: (interventionId: string) => Promise<void>;
  isAcknowledged: (interventionId: string) => boolean;
  testVoiceAlert: () => void;
  handleIntervention: (inv: Intervention) => void;
  handleResolution: (category: string) => void;
  resetSession: () => void;
}

const DEFAULT_PREFERENCES: UserPreferences = {
  browser_notifications_enabled: false,
  voice_alerts_enabled: false,
  voice_volume: 0.8,
  voice_rate: 1.0,
  voice_pitch: 1.0,
  quiet_mode_enabled: false,
  selected_voice: null,
  data_retention_days: undefined,
  alert_language: "en",
};

const AlertContext = createContext<AlertContextValue | null>(null);

export const AlertProvider: React.FC<{ children: React.ReactNode; apiBase?: string }> = ({ children, apiBase = "" }) => {
  const { user, token } = useAuth();

  // Transient runtime state (never saved to database)
  const [isMuted, setIsMuted] = useState<boolean>(false);

  // Persistent preferences state
  const [preferences, setPreferences] = useState<UserPreferences>(DEFAULT_PREFERENCES);
  const [browserPermission, setBrowserPermission] = useState<NotificationPermission>(
    notificationService.getPermission()
  );
  const [availableVoices, setAvailableVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [acknowledgedAlertIds, setAcknowledgedAlertIds] = useState<Set<string>>(new Set());

  // Ref to prevent race conditions or repeated deliveries
  const dispatchedIds = useRef<Set<string>>(new Set());

  // Load available voices
  useEffect(() => {
    speechProvider.getVoices().then((voices) => {
      setAvailableVoices(voices);
    });
  }, []);

  // Fetch preferences when authenticated
  useEffect(() => {
    if (!user || !token) {
      return;
    }

    let isMounted = true;
    const fetchUserPreferences = async () => {
      try {
        const resp = await apiFetch(`${apiBase}/api/v1/user/preferences`);
        if (resp.ok) {
          const data = await resp.json();
          if (isMounted) {
            setPreferences((prev) => ({
              ...prev,
              browser_notifications_enabled: data.browser_notifications_enabled ?? prev.browser_notifications_enabled,
              voice_alerts_enabled: data.voice_alerts_enabled ?? prev.voice_alerts_enabled,
              voice_volume: data.voice_volume ?? prev.voice_volume,
              voice_rate: data.voice_rate ?? prev.voice_rate,
              voice_pitch: data.voice_pitch ?? prev.voice_pitch,
              quiet_mode_enabled: data.quiet_mode_enabled ?? prev.quiet_mode_enabled,
              selected_voice: data.selected_voice ?? prev.selected_voice,
              data_retention_days: data.data_retention_days ?? prev.data_retention_days,
              alert_language: data.alert_language ?? prev.alert_language ?? "en",
            }));
          }
        }
      } catch (err) {
        console.warn("Could not fetch remote user preferences, using local defaults:", err);
      }
    };

    fetchUserPreferences();
    return () => {
      isMounted = false;
    };
  }, [user, token, apiBase]);

  // Toggle Mute (transient runtime action)
  const toggleMute = useCallback(() => {
    setIsMuted((prev) => {
      const next = !prev;
      if (next) {
        voiceQueue.clearAll();
      }
      return next;
    });
  }, []);

  // Update persistent preferences via VisionGuard API
  const updatePreferences = useCallback(
    async (updates: Partial<UserPreferences>) => {
      setPreferences((prev) => ({ ...prev, ...updates }));

      if (!token) return;

      try {
        await apiFetch(`${apiBase}/api/v1/user/preferences`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(updates),
        });
      } catch (err) {
        console.error("Failed to persist user preferences to backend:", err);
      }
    },
    [token, apiBase]
  );

  // Set Quiet Mode helper
  const setQuietMode = useCallback(
    async (enabled: boolean) => {
      if (enabled) {
        voiceQueue.clearAll();
      }
      await updatePreferences({ quiet_mode_enabled: enabled });
    },
    [updatePreferences]
  );

  // Set Alert Language helper
  const setAlertLanguage = useCallback(
    async (lang: "en" | "ta" | "en+ta") => {
      await updatePreferences({ alert_language: lang });
    },
    [updatePreferences]
  );

  // Request browser notification permission
  const requestBrowserNotifications = useCallback(async (): Promise<boolean> => {
    const granted = await notificationService.requestPermission();
    setBrowserPermission(notificationService.getPermission());
    if (granted) {
      await updatePreferences({ browser_notifications_enabled: true });
      return true;
    }
    return false;
  }, [updatePreferences]);

  // Acknowledge alert
  const acknowledgeAlert = useCallback(
    async (interventionId: string) => {
      setAcknowledgedAlertIds((prev) => new Set(prev).add(interventionId));

      if (!token) return;
      try {
        await apiFetch(`${apiBase}/api/v1/user/alerts/acknowledge`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ intervention_id: interventionId }),
        });
      } catch (err) {
        console.error("Failed to acknowledge alert on backend:", err);
      }
    },
    [token, apiBase]
  );

  const isAcknowledged = useCallback(
    (interventionId: string) => acknowledgedAlertIds.has(interventionId),
    [acknowledgedAlertIds]
  );

  // Test Voice Alert
  const testVoiceAlert = useCallback(() => {
    if (isMuted) return;
    const lang = preferences.alert_language || "en";
    let testText = "Please adjust your sitting posture.";
    if (lang === "ta") {
      testText = "உங்கள் அமரும் தோரணையை சரிசெய்யவும்.";
    } else if (lang === "en+ta") {
      testText = "Please adjust your sitting posture. உங்கள் அமரும் தோரணையை சரிசெய்யவும்.";
    }

    voiceQueue.enqueue(
      {
        id: `test-voice-${Date.now()}`,
        text: testText,
        audioKey: "posture_moderate",
        language: lang,
        priority: "HIGH",
        category: "SYSTEM",
        timestamp: Date.now(),
      },
      () => ({
        volume: preferences.voice_volume,
        rate: preferences.voice_rate,
        pitch: preferences.voice_pitch,
        voiceName: preferences.selected_voice,
      })
    );
  }, [isMuted, preferences]);

  // Process incoming intervention from WebSocket
  const handleIntervention = useCallback(
    (inv: Intervention) => {
      if (!inv || inv.level === "LOW" || inv.level === "UNKNOWN") {
        return;
      }

      // Check delivery-level deduplication
      if (dispatchedIds.current.has(inv.intervention_id)) {
        return;
      }
      dispatchedIds.current.add(inv.intervention_id);

      // 1. Voice Delivery
      // Condition: not quiet mode, not muted, voice_alerts_enabled, valid speech
      if (!preferences.quiet_mode_enabled && !isMuted && preferences.voice_alerts_enabled) {
        const priority = inv.level === "HIGH" ? "HIGH" : "NORMAL";
        const cat = (inv.category || "").toLowerCase();
        const lvl = (inv.level || "").toLowerCase();
        let audioKey: string | undefined = undefined;
        if (cat === "posture" || cat === "alertness") {
          audioKey = `${cat}_${lvl}`;
        }

        voiceQueue.enqueue(
          {
            id: inv.intervention_id,
            text: inv.message,
            audioKey,
            language: preferences.alert_language || "en",
            priority,
            category: inv.category,
            timestamp: Date.now(),
          },
          () => ({
            volume: preferences.voice_volume,
            rate: preferences.voice_rate,
            pitch: preferences.voice_pitch,
            voiceName: preferences.selected_voice,
          })
        );
      }

      // 2. Desktop Notification Delivery
      if (!preferences.quiet_mode_enabled && preferences.browser_notifications_enabled) {
        notificationService.showNotification(inv.title, { body: inv.message, category: inv.category });
      }
    },
    [isMuted, preferences]
  );

  // Handle RESOLVED state
  const handleResolution = useCallback((category: string) => {
    voiceQueue.clearCategory(category);
  }, []);

  // Reset all transient state on session stop
  const resetSession = useCallback(() => {
    voiceQueue.clearAll();
    notificationService.resetCooldowns();
    dispatchedIds.current.clear();
    setAcknowledgedAlertIds(new Set());
  }, []);

  // Cleanup on signout
  useEffect(() => {
    if (!user) {
      voiceQueue.clearAll();
      dispatchedIds.current.clear();
      setAcknowledgedAlertIds(new Set());
    }
  }, [user]);

  const value: AlertContextValue = {
    isMuted,
    quietModeEnabled: preferences.quiet_mode_enabled,
    voiceAlertsEnabled: preferences.voice_alerts_enabled,
    voiceVolume: preferences.voice_volume,
    voiceRate: preferences.voice_rate,
    voicePitch: preferences.voice_pitch,
    selectedVoice: preferences.selected_voice,
    alertLanguage: preferences.alert_language || "en",
    browserNotificationsEnabled: preferences.browser_notifications_enabled,
    browserPermission,
    availableVoices,
    acknowledgedAlertIds,
    toggleMute,
    setQuietMode,
    setAlertLanguage,
    updatePreferences,
    requestBrowserNotifications,
    acknowledgeAlert,
    isAcknowledged,
    testVoiceAlert,
    handleIntervention,
    handleResolution,
    resetSession,
  };

  return <AlertContext.Provider value={value}>{children}</AlertContext.Provider>;
};

export const useAlerts = (): AlertContextValue => {
  const context = useContext(AlertContext);
  if (!context) {
    throw new Error("useAlerts must be used within an AlertProvider");
  }
  return context;
};
