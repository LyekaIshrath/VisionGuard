import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { Intervention, UserPreferences } from "../types";
import { speechProvider } from "../services/voiceAlertProvider";
import { voiceQueue } from "../services/voiceQueue";
import { notificationService } from "../services/browserNotifications";
import { useAuth } from "./AuthContext";

interface AlertContextValue {
  isMuted: boolean;
  quietModeEnabled: boolean;
  voiceAlertsEnabled: boolean;
  voiceVolume: number;
  voiceRate: number;
  voicePitch: number;
  selectedVoice: string | null;
  browserNotificationsEnabled: boolean;
  browserPermission: NotificationPermission;
  availableVoices: SpeechSynthesisVoice[];
  acknowledgedAlertIds: Set<string>;
  toggleMute: () => void;
  setQuietMode: (enabled: boolean) => Promise<void>;
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
  voice_alerts_enabled: true,
  voice_volume: 0.8,
  voice_rate: 1.0,
  voice_pitch: 1.0,
  quiet_mode_enabled: false,
  selected_voice: null,
  timezone: null,
};

const AlertContext = createContext<AlertContextValue | null>(null);

export const AlertProvider: React.FC<{ children: React.ReactNode; apiBase?: string }> = ({
  children,
  apiBase = "http://localhost:8000",
}) => {
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

    fetch(`${apiBase}/api/v1/user/preferences`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })
      .then((res) => {
        if (res.ok) return res.json();
        return null;
      })
      .then((data) => {
        if (data && data.preferences) {
          setPreferences((prev) => ({
            ...prev,
            ...data.preferences,
          }));
        }
      })
      .catch((err) => console.warn("Failed to load user preferences:", err));
  }, [user, token, apiBase]);

  // Toggle Mute: transient runtime toggle that immediately cancels active & queued speech
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
        await fetch(`${apiBase}/api/v1/user/preferences`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(updates),
        });
      } catch (err) {
        console.error("Failed to persist user preferences:", err);
      }
    },
    [token, apiBase]
  );

  const setQuietMode = useCallback(
    async (enabled: boolean) => {
      if (enabled) {
        // Quiet mode immediately clears any pending speech
        voiceQueue.clearAll();
      }
      await updatePreferences({ quiet_mode_enabled: enabled });
    },
    [updatePreferences]
  );

  // Request browser notifications on explicit user button click
  const requestBrowserNotifications = useCallback(async (): Promise<boolean> => {
    const perm = await notificationService.requestPermission();
    setBrowserPermission(perm);
    if (perm === "granted") {
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
        await fetch(`${apiBase}/api/v1/user/alerts/acknowledge`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
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
    const testPhrase = "This is a VisionGuard voice alert test.";
    voiceQueue.enqueue(
      {
        id: `test-voice-${Date.now()}`,
        text: testPhrase,
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
        voiceQueue.enqueue(
          {
            id: inv.intervention_id,
            text: inv.message,
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

      // 2. Browser Notification Delivery
      // Authoritative: Notification.permission === 'granted', preferences enabled, not in quiet mode
      if (
        !preferences.quiet_mode_enabled &&
        preferences.browser_notifications_enabled &&
        notificationService.getPermission() === "granted"
      ) {
        notificationService.showNotification(`VisionGuard: ${inv.title}`, {
          body: inv.message,
          category: inv.category,
          tag: inv.category,
        });
      }
    },
    [preferences, isMuted]
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
    browserNotificationsEnabled: preferences.browser_notifications_enabled,
    browserPermission,
    availableVoices,
    acknowledgedAlertIds,
    toggleMute,
    setQuietMode,
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
