import { AlertPriority, RiskCategory } from "../types";
import { VoiceOptions, speechProvider } from "./voiceAlertProvider";
import { naturalAudioProvider } from "./naturalAudioAlertProvider";

export interface VoiceQueueItem {
  id: string; // intervention_id or event key
  text: string;
  audioKey?: string; // e.g. "posture_moderate", "posture_high", "alertness_moderate", "alertness_high"
  language?: "en" | "ta" | "en+ta";
  priority: AlertPriority;
  category: RiskCategory | "SYSTEM";
  timestamp: number;
}

export class VoiceQueue {
  private queue: VoiceQueueItem[] = [];
  private activeItem: VoiceQueueItem | null = null;
  private isProcessing = false;
  private maxQueueSize = 5;

  enqueue(item: VoiceQueueItem, optionsGetter: () => VoiceOptions): boolean {
    // 1. Deduplication: reject if identical id is active or already queued
    if (this.activeItem && this.activeItem.id === item.id) {
      return false;
    }
    if (this.queue.some((q) => q.id === item.id)) {
      return false;
    }

    // 2. Priority handling: HIGH priority preemption removes queued non-HIGH items
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
      const lang = item.language || opts.language || "en";

      // 1. If audioKey provided, attempt primary Natural Audio playback
      if (item.audioKey) {
        const played = await naturalAudioProvider.playAlert(item.audioKey, lang, {
          volume: opts.volume,
          rate: opts.rate,
        });
        if (played) {
          return;
        }
      }

      // 2. Fallback to SpeechSynthesis (only if appropriate for language)
      if (lang === "ta") {
        // Never synthesize Tamil using English speech engine
        console.warn("[VoiceQueue] Tamil audio asset missing or failed; suppressing English synthesizer fallback.");
      } else if (lang === "en+ta") {
        // In bilingual mode, if Tamil asset failed, at least speak English cleanly if available
        await speechProvider.speak(item.text, opts, "en");
      } else {
        await speechProvider.speak(item.text, opts, "en");
      }
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
      naturalAudioProvider.cancel();
      speechProvider.cancel();
      this.activeItem = null;
      this.isProcessing = false;
    }
  }

  clearAll(): void {
    this.queue = [];
    this.activeItem = null;
    this.isProcessing = false;
    naturalAudioProvider.cancel();
    speechProvider.cancel();
  }

  getQueueLength(): number {
    return this.queue.length;
  }

  getActiveItem(): VoiceQueueItem | null {
    return this.activeItem;
  }
}

export const voiceQueue = new VoiceQueue();
