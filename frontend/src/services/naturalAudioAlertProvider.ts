/**
 * VisionGuard Natural Audio Alert Provider.
 *
 * Primary provider for fixed deterministic wellness and safety alerts.
 * Plays studio-quality pre-rendered neural audio assets for English (en),
 * Tamil (ta), and sequential bilingual (en+ta).
 *
 * Rules:
 *  - Deterministic sequential playback for en+ta (non-overlapping).
 *  - Never falls back to English speech for Tamil alerts.
 *  - If audio asset cannot play, provides safe silent/visual completion.
 */

export interface AudioPlayOptions {
  volume?: number;
  rate?: number;
  language?: "en" | "ta" | "en+ta";
  audioKey?: string;
}

export class NaturalAudioAlertProvider {
  private currentAudio: HTMLAudioElement | null = null;
  private isCurrentlyPlaying = false;
  private abortController: AbortController | null = null;
  private isAudioUnlocked = false;

  isAvailable(): boolean {
    return typeof window !== "undefined" && typeof Audio !== "undefined";
  }

  isSpeaking(): boolean {
    return this.isCurrentlyPlaying;
  }

  /**
   * Unlock audio playback context on a user gesture (e.g. Start Monitoring or Settings click).
   */
  unlockAudio(): void {
    if (this.isAudioUnlocked || !this.isAvailable()) return;
    try {
      const silentAudio = new Audio();
      silentAudio.src = "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA";
      silentAudio.volume = 0.01;
      silentAudio.play().then(() => {
        this.isAudioUnlocked = true;
      }).catch(() => {});
    } catch {}
  }

  cancel(): void {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    if (this.currentAudio) {
      try {
        this.currentAudio.pause();
        this.currentAudio.currentTime = 0;
      } catch {}
      this.currentAudio = null;
    }
    this.isCurrentlyPlaying = false;
  }

  /**
   * Play an audio asset from /audio/alerts/{lang}/{audioKey}.mp3.
   */
  private playAsset(lang: "en" | "ta", audioKey: string, volume: number = 0.8, signal?: AbortSignal): Promise<boolean> {
    return new Promise((resolve) => {
      if (signal?.aborted) {
        return resolve(false);
      }

      // Root-relative path resolved by Vite public server
      const audioUrl = `/audio/alerts/${lang}/${audioKey}.mp3`;
      const audio = new Audio(audioUrl);
      this.currentAudio = audio;
      audio.volume = Math.max(0, Math.min(1, volume));

      const cleanup = () => {
        audio.onended = null;
        audio.onerror = null;
        if (this.currentAudio === audio) {
          this.currentAudio = null;
        }
      };

      audio.onended = () => {
        cleanup();
        resolve(true);
      };

      audio.onerror = () => {
        console.warn(`[NaturalAudio] Failed to load audio asset: ${audioUrl}`);
        cleanup();
        resolve(false);
      };

      if (signal) {
        signal.addEventListener("abort", () => {
          try {
            audio.pause();
          } catch {}
          cleanup();
          resolve(false);
        });
      }

      audio.play().catch((err) => {
        console.warn(`[NaturalAudio] Playback error for ${lang}/${audioKey}:`, err);
        cleanup();
        resolve(false);
      });
    });
  }

  /**
   * Deterministic alert playback for en, ta, or sequential bilingual en+ta.
   */
  async playAlert(
    audioKey: string,
    language: "en" | "ta" | "en+ta",
    options: AudioPlayOptions = {}
  ): Promise<boolean> {
    this.cancel();
    this.abortController = new AbortController();
    const signal = this.abortController.signal;
    this.isCurrentlyPlaying = true;
    const vol = options.volume !== undefined ? options.volume : 0.8;

    try {
      if (language === "en") {
        return await this.playAsset("en", audioKey, vol, signal);
      } else if (language === "ta") {
        return await this.playAsset("ta", audioKey, vol, signal);
      } else if (language === "en+ta") {
        const enSuccess = await this.playAsset("en", audioKey, vol, signal);
        if (signal.aborted) return false;

        await new Promise((r) => setTimeout(r, 300));
        if (signal.aborted) return false;

        const taSuccess = await this.playAsset("ta", audioKey, vol, signal);
        return enSuccess || taSuccess;
      }
      return false;
    } finally {
      this.isCurrentlyPlaying = false;
      this.currentAudio = null;
    }
  }
}

export const naturalAudioProvider = new NaturalAudioAlertProvider();
