/**
 * JARVIS — Voice Pipeline
 * Web Audio API for playback, mic capture, audio queue, interrupt handling.
 * Web Speech API for dictation (speech-to-text) — fallback mode.
 * MicRecorder for raw audio capture — backend Whisper transcription mode.
 *
 * Built from CLAUDE.md by RJ - https://itsbrook.com
 */

import { MicRecorder } from './mic-recorder';

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

  // Speech-to-text (dictation — Web Speech API fallback)
  private recognition: any = null;
  private onTranscript: ((text: string) => void) | null = null;
  private onDictationEnd: (() => void) | null = null;

  // Raw mic capture (backend Whisper mode)
  private micRecorder: MicRecorder | null = null;
  private onAudioChunk: ((data: ArrayBuffer) => void) | null = null;

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
      // Check if getUserMedia is available (requires HTTPS or localhost)
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        console.warn('[Voice] Microphone not available — requires HTTPS or localhost');
        return;
      }
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
    this.stopBackendSTT();
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
  }

  // ---- Backend Whisper Mode (raw audio capture) ----

  /**
   * Check if backend Whisper mode is available (MediaRecorder + WebSocket).
   */
  static hasBackendSTT(): boolean {
    return MicRecorder.isSupported();
  }

  /**
   * Start raw mic capture for backend Whisper transcription.
   * Audio chunks are sent via onAudioChunk callback.
   */
  async startBackendSTT(
    onAudioChunk: (data: ArrayBuffer) => void,
    onLevel: (level: number) => void,
    onError: (err: string) => void
  ): Promise<void> {
    if (!this.micRecorder) {
      this.micRecorder = new MicRecorder();
    }
    this.onAudioChunk = onAudioChunk;
    await this.micRecorder.start(
      (data) => {
        if (this.onAudioChunk) this.onAudioChunk(data);
      },
      onLevel,
      onError
    );
  }

  /**
   * Stop backend STT capture.
   */
  stopBackendSTT(): void {
    if (this.micRecorder) {
      this.micRecorder.stop();
    }
    this.onAudioChunk = null;
  }

  /**
   * Get mic level from backend STT recorder.
   */
  getBackendSTTLevel(): number {
    return this.micRecorder?.getLevel() ?? 0;
  }

  /**
   * Whether backend STT is actively recording.
   */
  get backendSTTActive(): boolean {
    return this.micRecorder?.recording ?? false;
  }

  // ---- Dictation (Web Speech API — fallback) ----

  /**
   * Check if dictation is available in this browser.
   */
  static hasDictation(): boolean {
    return !!(window.SpeechRecognition || (window as any).webkitSpeechRecognition);
  }

  /**
   * Start dictation. Calls onResult with interim/final transcripts.
   */
  startDictation(
    onResult: (text: string, isFinal: boolean) => void,
    onEnd: () => void,
    onError: (err: string) => void
  ): void {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      onError('Speech recognition not supported in this browser');
      return;
    }

    // Stop any existing recognition
    this.stopDictation();

    this.recognition = new SpeechRecognition();
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.lang = 'en-US';

    this.recognition.onresult = (event: any) => {
      let finalText = '';
      let interimText = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalText += transcript;
        } else {
          interimText += transcript;
        }
      }
      if (finalText) {
        onResult(finalText, true);
      } else if (interimText) {
        onResult(interimText, false);
      }
    };

    this.recognition.onerror = (event: any) => {
      onError(event.error || 'Unknown error');
    };

    this.recognition.onend = () => {
      onEnd();
    };

    this.recognition.start();
  }

  /**
   * Stop dictation.
   */
  stopDictation(): void {
    if (this.recognition) {
      this.recognition.stop();
      this.recognition = null;
    }
  }
}