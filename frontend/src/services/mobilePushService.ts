/**
 * VisionGuard Mobile Push Service.
 *
 * Interfaces with the Service Worker PushManager to register mobile browser / PWA
 * push subscriptions and synchronize device metadata with the VisionGuard backend.
 */

import { apiFetch } from "./apiClient";

export interface RegisteredDevice {
  device_id: string;
  platform: string;
  device_name: string;
  enabled: boolean;
  last_seen_at?: string;
  created_at?: string;
}

export interface PushSupportStatus {
  supported: boolean;
  serviceWorkerReady: boolean;
  permission: NotificationPermission;
  hasSubscription: boolean;
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/\-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

export class MobilePushService {
  isPushSupported(): boolean {
    return (
      typeof window !== "undefined" &&
      "serviceWorker" in navigator &&
      "PushManager" in window &&
      "Notification" in window
    );
  }

  async checkStatus(): Promise<PushSupportStatus> {
    if (!this.isPushSupported()) {
      return {
        supported: false,
        serviceWorkerReady: false,
        permission: "default",
        hasSubscription: false,
      };
    }

    const reg = await navigator.serviceWorker.getRegistration();
    const sub = reg ? await reg.pushManager.getSubscription() : null;

    return {
      supported: true,
      serviceWorkerReady: !!reg,
      permission: Notification.permission,
      hasSubscription: !!sub,
    };
  }

  async registerCurrentDevice(deviceName: string = "My Mobile Device"): Promise<boolean> {
    if (!this.isPushSupported()) {
      throw new Error("Push notifications are not supported in this browser.");
    }

    // 1. Request notification permission from user gesture
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      throw new Error("Notification permission was not granted.");
    }

    // 2. Fetch VAPID public key from backend
    const keyRes = await apiFetch("/api/v1/notifications/vapid-public-key");
    const keyData = await keyRes.json();
    const vapidKey = keyData?.public_key;
    if (!vapidKey) {
      throw new Error("Failed to retrieve VAPID key from VisionGuard server.");
    }

    // 3. Obtain push subscription from Service Worker
    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();

    if (!subscription) {
      const convertedKey = urlBase64ToUint8Array(vapidKey);
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: convertedKey as unknown as BufferSource,
      });
    }

    // Determine platform
    const ua = navigator.userAgent.toLowerCase();
    const platform = /iphone|ipad|ipod/.test(ua)
      ? "ios"
      : /android/.test(ua)
      ? "android"
      : "web_mobile";

    // 4. Register with backend
    await apiFetch("/api/v1/notifications/devices/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform,
        device_name: deviceName,
        push_subscription: subscription.toJSON(),
      }),
    });

    return true;
  }

  async listDevices(): Promise<RegisteredDevice[]> {
    try {
      const res = await apiFetch("/api/v1/notifications/devices");
      if (!res.ok) return [];
      return (await res.json()) || [];
    } catch {
      return [];
    }
  }

  async unregisterDevice(deviceId: string): Promise<boolean> {
    const res = await apiFetch(`/api/v1/notifications/devices/${deviceId}`, {
      method: "DELETE",
    });
    return res.ok;
  }

  async sendTestPush(): Promise<{ delivered: number; targeted: number }> {
    const res = await apiFetch("/api/v1/notifications/test-mobile", {
      method: "POST",
    });
    const data = await res.json();
    const summary = data?.delivery_summary;
    return {
      delivered: summary?.delivered || 0,
      targeted: summary?.targeted_devices || 0,
    };
  }
}

export const mobilePushService = new MobilePushService();
