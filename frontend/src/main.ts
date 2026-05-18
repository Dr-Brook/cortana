/**
 * JARVIS — Main State Machine
 * States: idle → listening → thinking → speaking
 * Wake word detection, mic permission, visual state transitions.
 *
 * Built from CLAUDE.md by RJ - https://itsbrook.com
 */

import { JarvisOrb } from './orb';
import { WSClient, WS_BASE } from './ws';
import { VoicePipeline } from './voice';
import { SettingsManager } from './settings';
import './style.css';

type State = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

class JarvisApp {
  private state: State = 'idle';
  private orb: JarvisOrb;
  private ws: WSClient;
  private voice: VoicePipeline;
  private settings: SettingsManager;
  private stateLabel: HTMLElement;
  private transcript: HTMLElement;
  private micButton: HTMLElement;
  private statusDot: HTMLElement;
  private isListening = false;
  private currentResponse = '';

  constructor() {
    // Initialize UI elements
    this.stateLabel = document.getElementById('state-label')!;
    this.transcript = document.getElementById('transcript')!;
    this.micButton = document.getElementById('mic-button')!;
    this.statusDot = document.querySelector('#connection-status .dot')!;

    // Show WS URL on startup so user can see what's being attempted
    this.stateLabel.textContent = `Connecting to ${WS_BASE}...`;

    // Initialize components
    this.settings = new SettingsManager((settings) => this.onSettingsChange(settings));
    this.orb = new JarvisOrb('orb-container');
    this.voice = new VoicePipeline();
    this.ws = new WSClient({
      onStateChange: (state, sentiment) => this.onStateChange(state, sentiment),
      onMessage: (msg) => this.onMessage(msg),
      onAudio: (data) => this.onAudio(data),
      onOpen: () => this.onWSOpen(),
      onClose: () => this.onWSClose(),
      onError: () => this.onWSError(),
    });

    this.setupUI();
    this.settings.render();

    // Connect
    this.ws.connect();
  }

  private setupUI(): void {
    // Mic button — tap to dictate
    this.micButton.addEventListener('click', () => {
      if (this.isListening) {
        this.stopListening();
      } else {
        this.startListening();
      }
    });

    // Text input — type a message
    const textInput = document.getElementById('text-input') as HTMLInputElement;
    const sendBtn = document.getElementById('send-button') as HTMLButtonElement;

    const sendTextMessage = () => {
      const text = textInput.value.trim();
      if (!text) return;
      this.transcript.innerHTML = `<span class="user-text">${this.escapeHtml(text)}</span>`;
      this.ws.sendTranscript(text);
      textInput.value = '';
    };

    sendBtn.addEventListener('click', sendTextMessage);
    textInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        sendTextMessage();
      }
    });

    // Keyboard shortcut — spacebar to talk
    document.addEventListener('keydown', (e) => {
      if (e.code === 'Space' && !e.repeat) {
        e.preventDefault();
        this.startListening();
      }
    });
    document.addEventListener('keyup', (e) => {
      if (e.code === 'Space') {
        e.preventDefault();
        this.stopListening();
      }
    });

    // Escape to interrupt
    document.addEventListener('keydown', (e) => {
      if (e.code === 'Escape') {
        this.interrupt();
      }
    });

    // Update state label
    this.updateStateLabel();
  }

  private setState(newState: State): void {
    this.state = newState;
    this.updateStateLabel();

    // Update orb
    switch (newState) {
      case 'idle':
        this.orb.setSpeaking(false);
        this.orb.setListening(false);
        this.orb.setSentiment('neutral');
        this.orb.setEnergy(0);
        break;
      case 'listening':
        this.orb.setSpeaking(false);
        this.orb.setListening(true);
        this.orb.setSentiment('listening');
        this.orb.setEnergy(0.3);
        break;
      case 'thinking':
        this.orb.setSpeaking(false);
        this.orb.setListening(false);
        this.orb.setSentiment('thinking');
        this.orb.setEnergy(0.2);
        break;
      case 'speaking':
        this.orb.setSpeaking(true);
        this.orb.setListening(false);
        this.orb.setSentiment('positive');
        this.orb.setEnergy(0.5);
        break;
      case 'error':
        this.orb.setSpeaking(false);
        this.orb.setListening(false);
        this.orb.setSentiment('negative');
        this.orb.setEnergy(0.1);
        break;
    }
  }

  private updateStateLabel(): void {
    const labels: Record<State, string> = {
      idle: 'Tap the mic to speak',
      listening: 'Listening...',
      thinking: 'Thinking...',
      speaking: 'Speaking...',
      error: 'Error',
    };
    this.stateLabel.textContent = labels[this.state];
    this.stateLabel.className = this.state;
  }

  // ---- Mic Handling ----

  private async startListening(): Promise<void> {
    if (this.state === 'speaking' || this.state === 'thinking') {
      this.interrupt();
      return;
    }

    // Prefer backend Whisper STT (privacy + offline) when available
    if (VoicePipeline.hasBackendSTT()) {
      this.isListening = true;
      this.setState('listening');
      (this.micButton as HTMLElement).classList.add('active');

      // Start audio stream
      this.ws.startAudioStream();

      // Accumulate audio chunks, send as binary frames
      let chunkCount = 0;
      await this.voice.startBackendSTT(
        (data) => {
          // Gate: don't send audio chunks while JARVIS is speaking
          if (this.state === 'speaking') return;
          this.ws.sendAudioChunk(data);
          chunkCount++;
        },
        (level) => {
          // Update orb energy with mic level
          this.orb.setEnergy(Math.max(0.2, level));
        },
        (err) => {
          console.error('[JARVIS] Backend STT error:', err);
          this.isListening = false;
          (this.micButton as HTMLElement).classList.remove('active');
          // Fall back to Web Speech API
          this.startDictation();
        }
      );

      this.transcript.innerHTML = '<span class="user-text">Listening... (backend STT)</span>';
      return;
    }

    // Fallback: Web Speech API dictation
    if (VoicePipeline.hasDictation()) {
      this.startDictation();
      return;
    }

    // Last resort: mic capture (requires HTTPS)
    try {
      await this.voice.startMicCapture();
      this.isListening = true;
      this.setState('listening');
      (this.micButton as HTMLElement).classList.add('active');
    } catch (e) {
      console.error('[JARVIS] Mic access denied:', e);
      this.setState('idle');
      this.transcript.innerHTML = 'Tap mic to dictate, or type below';
    }
  }

  private startDictation(): void {
    this.isListening = true;
    this.setState('listening');
    (this.micButton as HTMLElement).classList.add('active');

    let finalText = '';
    this.voice.startDictation(
      (text, isFinal) => {
        if (isFinal) {
          finalText += (finalText ? ' ' : '') + text;
          this.transcript.innerHTML = `<span class="user-text">${this.escapeHtml(finalText)}</span>`;
        } else {
          this.transcript.innerHTML = `<span class="user-text">${this.escapeHtml(finalText ? finalText + ' ' + text : text)}...</span>`;
        }
      },
      () => {
        this.isListening = false;
        (this.micButton as HTMLElement).classList.remove('active');
        if (finalText.trim()) {
          this.ws.sendTranscript(finalText.trim());
        } else {
          this.setState('idle');
        }
      },
      (err) => {
        console.error('[JARVIS] Dictation error:', err);
        this.isListening = false;
        (this.micButton as HTMLElement).classList.remove('active');
        this.setState('idle');
        this.transcript.innerHTML = 'Tap mic to dictate, or type below';
      }
    );
  }

  private stopListening(): void {
    if (!this.isListening) return;
    this.isListening = false;

    // Stop backend STT if active
    if (this.voice.backendSTTActive) {
      this.voice.stopBackendSTT();
      this.ws.endAudioStream();
    } else {
      this.voice.stopDictation();
    }

    (this.micButton as HTMLElement).classList.remove('active');
  }

  private interrupt(): void {
    this.ws.sendInterrupt();
    this.voice.interrupt();
    this.setState('idle');
    this.transcript.innerHTML = '';
    this.currentResponse = '';
  }

  // ---- WebSocket Handlers ----

  private onStateChange(state: string, sentiment?: string): void {
    this.setState(state as State);
    if (sentiment) {
      this.orb.setSentiment(sentiment);
    }
  }

  private onMessage(msg: any): void {
    if (msg.type === 'text_chunk') {
      this.currentResponse += msg.text;
      // Voice-only: don't display response text, audio will play
      // Still track it for context/continuity
    } else if (msg.type === 'error') {
      this.transcript.innerHTML = `<span class="error-text">Error: ${this.escapeHtml(msg.message)}</span>`;
      this.setState('error');
    } else if (msg.type === 'history') {
      // Don't display history text either — voice-only
    }
  }

  private async onAudio(data: ArrayBuffer): Promise<void> {
    try {
      await this.voice.playAudio(data);
    } catch (e) {
      console.error('[JARVIS] Audio playback error:', e);
    }
  }

  private onWSOpen(): void {
    this.statusDot.classList.add('connected');
    this.setState('idle');
    this.transcript.innerHTML = '';
    const dbg = document.getElementById('debug-banner');
    if (dbg) dbg.textContent = '';
  }

  private onWSClose(): void {
    this.statusDot.classList.remove('connected');
    const dbg = document.getElementById('debug-banner');
    if (dbg) dbg.textContent = 'Disconnected — reconnecting...';
  }

  private onWSError(): void {
    this.setState('error');
    this.stateLabel.textContent = 'Connection lost';
    const dbg = document.getElementById('debug-banner');
    if (dbg) dbg.textContent = 'Connection error — check console';
  }

  // ---- Settings ----

  private onSettingsChange(settings: any): void {
    this.voice.setVolume(settings.volume);
  }

  // ---- Utility ----

  private escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  destroy(): void {
    this.ws.disconnect();
    this.voice.destroy();
    this.orb.destroy();
  }
}

// ---- Bootstrap ----
const appContainer = document.getElementById('app')!;

// Create UI structure
appContainer.innerHTML = `
  <div id="connection-status">
    <span class="dot"></span>
    <span>JARVIS</span>
  </div>
  <div id="debug-banner" style="position:fixed;bottom:80px;left:0;right:0;text-align:center;font-size:11px;color:#888;z-index:400;pointer-events:none;">Connecting...</div>
  <div id="orb-container"></div>
  <div id="state-label">Connecting...</div>
  <div id="transcript">Tap mic to speak or type below</div>
  <div id="text-input-container" style="display:flex; gap:8px; padding:0 20px; margin-bottom:10px;">
    <input id="text-input" type="text" placeholder="Type a message..." style="flex:1; padding:10px 14px; background:var(--bg-primary); color:var(--text-primary); border:1px solid rgba(255,255,255,0.2); border-radius:20px; font-size:14px; outline:none;" />
    <button id="send-button" style="padding:10px 16px; background:var(--accent-blue); color:white; border:none; border-radius:20px; cursor:pointer; font-size:14px;">Send</button>
  </div>
  <button id="mic-button" title="Push to talk (Space)">🎤</button>
  <div id="settings-backdrop" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:250;display:none;"></div>
  <button id="settings-toggle" title="Settings">⚙</button>
  <div id="settings-panel"></div>
`;

// Initialize app
const app = new JarvisApp();

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  app.destroy();
});