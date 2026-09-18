import { AlertPriority, RiskCategory } from "../types";
import { VoiceAlertProvider, VoiceOptions, speechProvider } from "./voiceAlertProvider";

export interface VoiceQueueItem {
  id: string; // intervention_id or event key
  text: string;
  priority: AlertPriority;
  category: RiskCategory | "SYSTEM";
  timestamp: number;
}

export class VoiceQueue {
  private queue: VoiceQueueItem[] = [];
  private activeItem: VoiceQueueItem | null = null;
  private isProcessing = false;
  private provider: VoiceAlertProvider;
  private maxQueueSize = 5;

  constructor(provider: VoiceAlertProvider = speechProvider) {
    this.provider = provider;
  }

  enqueue(item: VoiceQueueItem, optionsGetter: () => VoiceOptions): boolean {
    // 1. Deduplication: reject if identical id is active or already queued
    if (this.activeItem && this.activeItem.id === item.id) {
      return false;
    }
    if (this.queue.some((q) => q.id === item.id)) {
      return false;
    }

    // 2. Priority handling: HIGH priority removes any queued MODERATE/NORMAL/LOW items
    if (item.priority === "HIGH") {
      this.queue = this.queue.filter((q) => q.priority === "HIGH");
    }

    // 3. Max bounded queue size: 5
    if (this.queue.length >= this.maxQueueSize) {
      const nonHighIdx = this.queue.findIndex((q) => q.priority !== "HIGH");
      if (nonHighIdx !== -1) {
        this.queue.splice(nonHighIdx, 1);
      } else {
        this.queue.shift();
      }
    }

    this.queue.push(item);
    // Sort HIGH priority to front
    this.queue.sort((a, b) => {
      const pMap = { HIGH: 3, NORMAL: 2, LOW: 1 };
      return pMap[b.priority] - pMap[a.priority];
    });

    this.processNext(optionsGetter);
    return true;
  }

  private async processNext(optionsGetter: () => VoiceOptions): Promise<void> {
    if (this.isProcessing || this.queue.length === 0) {
      return;
    }

    this.isProcessing = true;
    const item = this.queue.shift();
    if (!item) {
      this.isProcessing = false;
      return;
    }

    this.activeItem = item;
    try {
      const opts = optionsGetter();
      await this.provider.speak(item.text, opts);
    } catch (err) {
      console.warn("VoiceQueue playback error:", err);
    } finally {
      this.activeItem = null;
      this.isProcessing = false;
      if (this.queue.length > 0) {
        this.processNext(optionsGetter);
      }
    }
  }

  clearCategory(category: string): void {
    this.queue = this.queue.filter((q) => q.category !== category);
    if (this.activeItem && this.activeItem.category === category) {
      this.provider.cancel();
      this.activeItem = null;
      this.isProcessing = false;
    }
  }

  clearAll(): void {
    this.queue = [];
    this.activeItem = null;
    this.isProcessing = false;
    this.provider.cancel();
  }

  getQueueLength(): number {
    return this.queue.length;
  }

  getActiveItem(): VoiceQueueItem | null {
    return this.activeItem;
  }
}

export const voiceQueue = new VoiceQueue();
