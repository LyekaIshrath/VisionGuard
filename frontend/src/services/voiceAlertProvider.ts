export interface VoiceOptions {
  volume?: number; // 0.0 to 1.0
  rate?: number;   // 0.5 to 2.0
  pitch?: number;  // 0.5 to 2.0
  voiceName?: string | null;
  language?: "en" | "ta" | "en+ta";
}

export interface VoiceAlertProvider {
  isAvailable(): boolean;
  getVoices(): Promise<SpeechSynthesisVoice[]>;
  speak(text: string, options?: VoiceOptions, language?: string): Promise<void>;
  cancel(): void;
  isSpeaking(): boolean;
}

export class BrowserSpeechSynthesisProvider implements VoiceAlertProvider {
  private synth: SpeechSynthesis | null = null;

  constructor() {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      this.synth = window.speechSynthesis;
    }
  }

  isAvailable(): boolean {
    return this.synth !== null;
  }

  async getVoices(): Promise<SpeechSynthesisVoice[]> {
    if (!this.synth) return [];
    const current = this.synth.getVoices();
    if (current.length > 0) return current;

    return new Promise((resolve) => {
      if (!this.synth) return resolve([]);
      const handler = () => {
        const v = this.synth?.getVoices() || [];
        resolve(v);
      };
      this.synth.onvoiceschanged = handler;
      setTimeout(() => {
        resolve(this.synth?.getVoices() || []);
      }, 500);
    });
  }

  speak(text: string, options: VoiceOptions = {}, language: string = "en"): Promise<void> {
    return new Promise((resolve) => {
      if (!this.synth) {
        return resolve();
      }

      // CRITICAL AUDIO RULE: Never synthesize Tamil using an English voice.
      if (language === "ta" || language === "ta-IN") {
        const voices = this.synth.getVoices();
        const hasTamilVoice = voices.some((v) => v.lang.toLowerCase().startsWith("ta"));
        if (!hasTamilVoice) {
          console.warn("[SpeechSynthesis] No native Tamil voice detected. Suppressing fake English synthesis.");
          return resolve();
        }
      }

      // Always cancel existing speech before starting new utterance
      this.synth.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      if (options.volume !== undefined) utterance.volume = Math.max(0, Math.min(1, options.volume));
      if (options.rate !== undefined) utterance.rate = Math.max(0.5, Math.min(2.0, options.rate));
      if (options.pitch !== undefined) utterance.pitch = Math.max(0.5, Math.min(2.0, options.pitch));

      if (language === "ta" || language === "ta-IN") {
        utterance.lang = "ta-IN";
      } else {
        utterance.lang = "en-US";
      }

      if (options.voiceName) {
        const voices = this.synth.getVoices();
        const found = voices.find((v) => v.name === options.voiceName);
        if (found) {
          utterance.voice = found;
        }
      } else {
        // Match exact language first
        const voices = this.synth.getVoices();
        const prefix = utterance.lang.split("-")[0].toLowerCase();
        const matching = voices.find((v) => v.lang.toLowerCase().startsWith(prefix));
        if (matching) {
          utterance.voice = matching;
        }
      }

      utterance.onend = () => resolve();
      utterance.onerror = (e) => {
        if (e.error !== "interrupted" && e.error !== "canceled") {
          console.warn("SpeechSynthesis error:", e.error);
        }
        resolve();
      };

      this.synth.speak(utterance);
    });
  }

  cancel(): void {
    if (this.synth) {
      this.synth.cancel();
    }
  }

  isSpeaking(): boolean {
    return this.synth ? this.synth.speaking : false;
  }
}

export const speechProvider = new BrowserSpeechSynthesisProvider();
