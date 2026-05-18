/**
 * JARVIS — WebSocket Client
 * Auto-reconnect with exponential backoff, JSON + binary handling.
 *
 * Built from CLAUDE.md by RJ - https://itsbrook.com
 */

// Dynamic WebSocket URL — uses the same host as the page.
// Caddy routes /ws to the backend.
// If accessing directly (localhost:3002), use port 8444.
export const WS_BASE = import.meta.env.VITE_WS_URL || (() => {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const isDev = window.location.port === '5173';
  const isDirect = window.location.port === '3002' || isDev;
  if (isDirect) {
    // Direct access — backend is on same host, port 8444
    return `${proto}//${window.location.hostname}:8444/ws`;
  }
  // Proxied via Caddy — same host, /ws path routes to backend
  return `${proto}//${window.location.host}/ws`;
})();

type MessageHandler = (msg: any) => void;
type AudioHandler = (data: ArrayBuffer) => void;

interface WSClientOptions {
  onMessage?: MessageHandler;
  onAudio?: AudioHandler;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (err: Event) => void;
  onStateChange?: (state: string, sentiment?: string) => void;
}

export class WSClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private messageBuffer: string[] = [];
  private audioBuffer: ArrayBuffer[] = [];
  private isReceivingAudio = false;
  private options: WSClientOptions;
  private pingInterval: ReturnType<typeof setInterval> | null = null;

  constructor(options: WSClientOptions = {}) {
    this.options = options;
  }

  connect(): void {
    try {
      console.log(`[WS] Connecting to: ${WS_BASE}`);
      this.ws = new WebSocket(WS_BASE);
      this.ws.binaryType = 'arraybuffer';

      this.ws.onopen = () => {
        console.log('[WS] Connected to JARVIS server');
        this.reconnectAttempts = 0;
        this.flushBuffer();
        this.startPing();
        this.options.onOpen?.();
      };

      this.ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          try {
            const msg = JSON.parse(event.data);
            this.handleMessage(msg);
          } catch {
            console.warn('[WS] Non-JSON text message:', event.data);
          }
        } else if (event.data instanceof ArrayBuffer) {
          this.handleBinaryData(event.data);
        }
      };

      this.ws.onclose = () => {
        console.log('[WS] Disconnected');
        this.stopPing();
        this.scheduleReconnect();
        this.options.onClose?.();
      };

      this.ws.onerror = (err) => {
        console.error('[WS] Error:', err);
        console.error('[WS] Error readyState:', this.ws?.readyState, 'URL:', this.ws?.url);
        this.options.onError?.(err);
      };
    } catch (e) {
      console.error('[WS] Connection failed:', e);
      this.scheduleReconnect();
    }
  }

  private handleMessage(msg: any): void {
    switch (msg.type) {
      case 'state':
        this.options.onStateChange?.(msg.state, msg.sentiment);
        break;
      case 'text_chunk':
        // Streaming text from LLM
        this.options.onMessage?.(msg);
        break;
      case 'audio_start':
        this.isReceivingAudio = true;
        this.audioBuffer = [];
        break;
      case 'audio_end':
        this.isReceivingAudio = false;
        if (this.audioBuffer.length > 0) {
          const totalLength = this.audioBuffer.reduce((acc, buf) => acc + buf.byteLength, 0);
          const combined = new Uint8Array(totalLength);
          let offset = 0;
          for (const buf of this.audioBuffer) {
            combined.set(new Uint8Array(buf), offset);
            offset += buf.byteLength;
          }
          this.options.onAudio?.(combined.buffer);
        }
        this.audioBuffer = [];
        break;
      case 'interrupted':
        this.audioBuffer = [];
        this.isReceivingAudio = false;
        this.options.onStateChange?.('idle');
        break;
      case 'error':
        console.error('[WS] Server error:', msg.message);
        this.options.onMessage?.(msg);
        break;
      case 'pong':
        // Heartbeat response
        break;
      default:
        this.options.onMessage?.(msg);
    }
  }

  private handleBinaryData(data: ArrayBuffer): void {
    if (this.isReceivingAudio) {
      this.audioBuffer.push(data);
    }
  }

  send(obj: object): void {
    const payload = JSON.stringify(obj);
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(payload);
    } else {
      this.messageBuffer.push(payload);
    }
  }

  sendAudio(data: ArrayBuffer): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(data);
    }
  }

  sendTranscript(text: string): void {
    this.send({ type: 'transcript', text });
  }

  sendInterrupt(): void {
    this.send({ type: 'interrupt' });
  }

  requestHistory(): void {
    this.send({ type: 'get_history' });
  }

  private flushBuffer(): void {
    while (this.messageBuffer.length > 0) {
      const msg = this.messageBuffer.shift()!;
      this.ws?.send(msg);
    }
  }

  private startPing(): void {
    this.pingInterval = setInterval(() => {
      this.send({ type: 'ping', timestamp: Date.now() / 1000 });
    }, 30000);
  }

  private stopPing(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('[WS] Max reconnect attempts reached');
      return;
    }

    // Exponential backoff: 1s, 2s, 4s, 8s, 16s...
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectAttempts++;

    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  disconnect(): void {
    this.stopPing();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}