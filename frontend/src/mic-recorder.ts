/**
 * JARVIS — Mic Recorder
 * Raw audio capture via MediaRecorder → WebSocket binary frames.
 * Replaces Web Speech API with backend Whisper transcription.
 *
 * Built from CLAUDE.md by RJ - https://itsbrook.com
 */

export class MicRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private onChunk: ((data: ArrayBuffer) => void) | null = null;
  private onLevel: ((level: number) => void) | null = null;
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private isRecording = false;

  /**
   * Check if MediaRecorder is available.
   */
  static isSupported(): boolean {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) && !!window['MediaRecorder'];
  }

  /**
   * Start recording. Audio chunks are sent via onChunk callback.
   */
  async start(
    onChunk: (data: ArrayBuffer) => void,
    onLevel: (level: number) => void,
    onError: (err: string) => void
  ): Promise<void> {
    if (this.isRecording) {
      this.stop();
    }

    this.onChunk = onChunk;
    this.onLevel = onLevel;

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          // Prefer 16kHz for Whisper
          sampleRate: 16000,
        },
      });

      // Audio level analyser
      this.audioContext = new AudioContext({ sampleRate: 16000 });
      const source = this.audioContext.createMediaStreamSource(this.stream);
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 256;
      source.connect(this.analyser);

      // Start level monitoring
      this._monitorLevel();

      // MediaRecorder — send chunks as they arrive
      // Use webm/opus if available, fallback to whatever is supported
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : '';

      this.mediaRecorder = mimeType
        ? new MediaRecorder(this.stream, { mimeType })
        : new MediaRecorder(this.stream);

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0 && this.onChunk) {
          event.data.arrayBuffer().then((buffer) => {
            this.onChunk!(buffer);
          });
        }
      };

      // Send chunks every 250ms for low-latency streaming
      this.mediaRecorder.start(250);
      this.isRecording = true;
    } catch (e) {
      console.error('[MicRecorder] Mic access denied:', e);
      onError('Microphone access denied');
    }
  }

  /**
   * Stop recording.
   */
  stop(): void {
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }
    this.mediaRecorder = null;

    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }

    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }

    this.analyser = null;
    this.isRecording = false;
    this.onChunk = null;
    this.onLevel = null;
  }

  /**
   * Get current mic level (0-1).
   */
  getLevel(): number {
    if (!this.analyser) return 0;
    const data = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteFrequencyData(data);
    const avg = data.reduce((sum, v) => sum + v, 0) / data.length;
    return avg / 255;
  }

  /**
   * Monitor audio level continuously.
   */
  private _monitorLevel(): void {
    const check = () => {
      if (!this.isRecording || !this.onLevel) return;
      this.onLevel(this.getLevel());
      requestAnimationFrame(check);
    };
    requestAnimationFrame(check);
  }

  get recording(): boolean {
    return this.isRecording;
  }
}