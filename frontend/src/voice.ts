/**
 * CORTANA — Voice Pipeline
 * Web Audio API for playback, mic capture, audio queue, interrupt handling.
 *
 * Built from CLAUDE.md by RJ - https://itsbrook.com
 */

export class VoicePipeline {
  private audioContext: AudioContext | null = null;
  private currentSource: AudioBufferSourceNode | null = null;
  private gainNode: GainNode | null = null;
  private analyser: AnalyserNode | null = null;
  private micStream: MediaStream | null = null;
  private micAnalyser: AnalyserNode | null = null;
  private isPlaying = false;
  private interruptRequested = false;
  private audioQueue: ArrayBuffer[] = [];
  private processingQueue = false;

  async init(): Promise<void> {
    this.audioContext = new AudioContext();
    this.gainNode = this.audioContext.createGain();
    this.gainNode.connect(this.audioContext.destination);

    this.analyser = this.audioContext.createAnalyser();
    this.analyser.fftSize = 256;
    this.gainNode.connect(this.analyser);
  }

  // ---- Playback ----

  async playAudio(audioData: ArrayBuffer): Promise<void> {
    if (!this.audioContext) await this.init();
    this.interruptRequested = false;

    try {
      const audioBuffer = await this.audioContext!.decodeAudioData(audioData.slice(0));
      const source = this.audioContext!.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this.gainNode!);
      this.currentSource = source;

      return new Promise<void>((resolve) => {
        source.onended = () => {
          this.isPlaying = false;
          this.currentSource = null;
          resolve();
        };
        source.start(0);
        this.isPlaying = true;
      });
    } catch (e) {
      console.error('[Voice] Playback error:', e);
      this.isPlaying = false;
    }
  }

  async enqueueAudio(audioData: ArrayBuffer): Promise<void> {
    this.audioQueue.push(audioData);
    if (!this.processingQueue) {
      this.processQueue();
    }
  }

  private async processQueue(): Promise<void> {
    if (this.processingQueue) return;
    this.processingQueue = true;

    while (this.audioQueue.length > 0 && !this.interruptRequested) {
      const data = this.audioQueue.shift()!;
      await this.playAudio(data);
    }

    this.processingQueue = false;
  }

  interrupt(): void {
    this.interruptRequested = true;
    if (this.currentSource) {
      try {
        this.currentSource.stop();
      } catch {
        // Already stopped
      }
      this.currentSource = null;
    }
    this.isPlaying = false;
    this.audioQueue = [];
    this.processingQueue = false;
  }

  setVolume(level: number): void {
    if (this.gainNode) {
      this.gainNode.gain.value = Math.max(0, Math.min(1, level));
    }
  }

  getVolume(): number {
    return this.gainNode?.gain.value ?? 1;
  }

  getAudioLevel(): number {
    if (!this.analyser) return 0;
    const data = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteFrequencyData(data);
    const avg = data.reduce((sum, v) => sum + v, 0) / data.length;
    return avg / 255;
  }

  // ---- Microphone ----

  async startMicCapture(): Promise<void> {
    try {
      this.micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      if (!this.audioContext) await this.init();

      const source = this.audioContext!.createMediaStreamSource(this.micStream);
      this.micAnalyser = this.audioContext!.createAnalyser();
      this.micAnalyser.fftSize = 256;
      source.connect(this.micAnalyser);
    } catch (e) {
      console.error('[Voice] Mic access denied:', e);
      throw e;
    }
  }

  stopMicCapture(): void {
    if (this.micStream) {
      this.micStream.getTracks().forEach((track) => track.stop());
      this.micStream = null;
    }
    this.micAnalyser = null;
  }

  getMicLevel(): number {
    if (!this.micAnalyser) return 0;
    const data = new Uint8Array(this.micAnalyser.frequencyBinCount);
    this.micAnalyser.getByteFrequencyData(data);
    const avg = data.reduce((sum, v) => sum + v, 0) / data.length;
    return avg / 255;
  }

  // ---- State ----

  get playing(): boolean {
    return this.isPlaying;
  }

  destroy(): void {
    this.interrupt();
    this.stopMicCapture();
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
  }
}