/**
 * JARVIS — Wake Word Detector
 * Uses openWakeWord WASM for "Hey Jarvis" detection.
 * Runs continuously in idle state, triggers listening when detected.
 *
 * Built from CLAUDE.md by RJ - https://itsbrook.com
 */

export interface WakeWordConfig {
  enabled: boolean;
  word: string;         // "jarvis" | "hey_jarvis" | custom
  sensitivity: number;  // 0.0 - 1.0
}

const DEFAULT_CONFIG: WakeWordConfig = {
  enabled: true,
  word: 'hey_jarvis',
  sensitivity: 0.5,
};

export class WakeWordDetector {
  private config: WakeWordConfig;
  private isRunning = false;
  private micStream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private onDetected: (() => void) | null = null;
  private onLevel: ((level: number) => void) | null = null;

  // openWakeWord WASM module (loaded dynamically)
  private oww: any = null;
  private detector: any = null;

  constructor(config: Partial<WakeWordConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /**
   * Check if openWakeWord WASM is available.
   * For now, we check if the browser supports the required APIs.
   */
  static async isSupported(): Promise<boolean> {
    try {
      // Check AudioWorklet support (needed for WASM audio processing)
      if (!window.AudioWorkletNode) return false;
      if (!navigator.mediaDevices?.getUserMedia) return false;

      // Try to load the openWakeWord WASM module
      // This will fail gracefully if not available
      try {
        const _pkg = 'openwakeword-wasm';
        const mod = await import(/* @vite-ignore */ _pkg).catch(() => null);
        return !!mod;
      } catch {
        // WASM module not installed yet — will use fallback
        return false;
      }
    } catch {
      return false;
    }
  }

  /**
   * Start listening for wake word.
   * Requires continuous mic access.
   */
  async start(
    onDetected: () => void,
    onLevel: (level: number) => void
  ): Promise<void> {
    if (this.isRunning) return;

    this.onDetected = onDetected;
    this.onLevel = onLevel;

    try {
      // Get continuous mic stream
      this.micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      this.audioContext = new AudioContext({ sampleRate: 16000 });
      const source = this.audioContext.createMediaStreamSource(this.micStream);

      // Try openWakeWord WASM
      const owwAvailable = await WakeWordDetector.isSupported();
      if (owwAvailable) {
        await this._startOWW(source);
      } else {
        // Fallback: use volume-based detection
        this._startVolumeDetection(source);
      }

      this.isRunning = true;
      console.log('[WakeWord] Detector started');
    } catch (e) {
      console.error('[WakeWord] Failed to start:', e);
    }
  }

  /**
   * Stop listening for wake word.
   */
  stop(): void {
    this.isRunning = false;

    if (this.micStream) {
      this.micStream.getTracks().forEach((track) => track.stop());
      this.micStream = null;
    }

    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }

    this.detector = null;
    this.onDetected = null;
    this.onLevel = null;
  }

  /**
   * Update configuration.
   */
  updateConfig(config: Partial<WakeWordConfig>): void {
    this.config = { ...this.config, ...config };
  }

  /**
   * Get current configuration.
   */
  getConfig(): WakeWordConfig {
    return { ...this.config };
  }

  get running(): boolean {
    return this.isRunning;
  }

  // ---- Internal Methods ----

  private async _startOWW(source: MediaStreamAudioSourceNode): Promise<void> {
    try {
      const _pkg = 'openwakeword-wasm';
      const OpenWakeWord = await import(/* @vite-ignore */ _pkg).catch(() => null);
      if (!OpenWakeWord?.default) {
        this._startVolumeDetection(source);
        return;
      }
      this.oww = new OpenWakeWord.default();
      await this.oww.init();

      this.detector = await this.oww.createDetector({
        model: this.config.word,
        sensitivity: this.config.sensitivity,
      });

      // Connect audio source to detector
      const processor = this.audioContext!.createScriptProcessor(4096, 1, 1);
      source.connect(processor);
      processor.connect(this.audioContext!.destination);

      processor.onaudioprocess = (event) => {
        if (!this.isRunning) return;

        const input = event.inputBuffer.getChannelData(0);
        const score = this.detector.process(input);

        // Update level
        const rms = Math.sqrt(input.reduce((sum, v) => sum + v * v, 0) / input.length);
        if (this.onLevel) this.onLevel(rms);

        // Check if wake word detected
        if (score >= this.config.sensitivity) {
          console.log('[WakeWord] Detected! Score:', score);
          if (this.onDetected) this.onDetected();
        }
      };
    } catch (e) {
      console.warn('[WakeWord] OWW WASM failed, using volume fallback:', e);
      this._startVolumeDetection(source);
    }
  }

  /**
   * Volume-based fallback wake word detection.
   * Detects when someone starts speaking (volume above threshold).
   * Not a real wake word detector, but better than nothing.
   */
  private _startVolumeDetection(source: MediaStreamAudioSourceNode): void {
    const analyser = this.audioContext!.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);

    const THRESHOLD = 0.08; // Volume threshold for "someone is speaking"
    const MIN_DURATION = 500; // Minimum speaking duration before triggering
    const COOLDOWN = 3000; // Cooldown after trigger to prevent re-trigger

    let speakingStart: number | null = null;
    let lastTrigger = 0;

    const check = () => {
      if (!this.isRunning) return;

      const data = new Float32Array(analyser.fftSize);
      analyser.getFloatTimeDomainData(data);
      const rms = Math.sqrt(data.reduce((sum, v) => sum + v * v, 0) / data.length);

      if (this.onLevel) this.onLevel(rms);

      const now = Date.now();

      if (rms > THRESHOLD) {
        if (!speakingStart) {
          speakingStart = now;
        } else if (now - speakingStart > MIN_DURATION && now - lastTrigger > COOLDOWN) {
          console.log('[WakeWord] Volume trigger (fallback mode)');
          lastTrigger = now;
          speakingStart = null;
          if (this.onDetected) this.onDetected();
        }
      } else {
        speakingStart = null;
      }

      requestAnimationFrame(check);
    };

    requestAnimationFrame(check);
    console.log('[WakeWord] Volume-based fallback detector active');
  }
}