export class BrowserNotificationService {
  private lastNotificationTime: Record<string, number> = {};
  private cooldownSec = 30; // 30s anti-spam cooldown per category

  isSupported(): boolean {
    return typeof window !== "undefined" && "Notification" in window;
  }

  getPermission(): NotificationPermission {
    if (!this.isSupported()) return "denied";
    return Notification.permission;
  }

  async requestPermission(): Promise<NotificationPermission> {
    if (!this.isSupported()) return "denied";
    try {
      const perm = await Notification.requestPermission();
      return perm;
    } catch (e) {
      console.error("Error requesting notification permission:", e);
      return "denied";
    }
  }

  showNotification(
    title: string,
    options: {
      body: string;
      category: string;
      tag?: string;
      icon?: string;
    }
  ): boolean {
    if (!this.isSupported() || Notification.permission !== "granted") {
      return false;
    }

    const now = Date.now() / 1000;
    const lastTime = this.lastNotificationTime[options.category] || 0;
    if (now - lastTime < this.cooldownSec) {
      return false;
    }

    try {
      new Notification(title, {
        body: options.body,
        tag: options.tag || options.category,
        icon: options.icon || "/favicon.ico",
      });
      this.lastNotificationTime[options.category] = now;
      return true;
    } catch (e) {
      console.error("Failed to show browser notification:", e);
      return false;
    }
  }

  showTestNotification(
    title: string = "VisionGuard Test Alert",
    body: string = "Desktop notifications are working correctly with real-time privacy."
  ): boolean {
    if (!this.isSupported() || Notification.permission !== "granted") {
      return false;
    }

    try {
      new Notification(title, {
        body,
        tag: "visionguard-test-notification",
        icon: "/favicon.ico",
      });
      return true;
    } catch (e) {
      console.error("Failed to show test browser notification:", e);
      return false;
    }
  }

  resetCooldowns(): void {
    this.lastNotificationTime = {};
  }
}

export const notificationService = new BrowserNotificationService();
