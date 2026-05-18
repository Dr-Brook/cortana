/**
 * CORTANA — Main State Machine
 * States: idle → listening → thinking → speaking
 * Wake word detection, mic permission, visual state transitions.
 *
 * Built from CLAUDE.md by RJ - https://itsbrook.com
 */

import { CortanaOrb } from './orb';
import { WSClient } from './ws';
import { VoicePipeline } from './voice';
import { SettingsManager } from './settings';
import './style.css';

type State = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

class CortanaApp {
  private state: State = 'idle';
  private orb: CortanaOrb;
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

    // Initialize components
    this.settings = new SettingsManager((settings) => this.onSettingsChange(settings));
    this.orb = new CortanaOrb('orb-container');
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
    // Mic button — push to talk
    this.micButton.addEventListener('mousedown', () => this.startListening());
    this.micButton.addEventListener('mouseup', () => this.stopListening());
    this.micButton.addEventListener('touchstart', (e) => {
      e.preventDefault();
      this.startListening();
    });
    this.micButton.addEventListener('touchend', () => this.stopListening());

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
      idle: 'Ready',
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

    try {
      await this.voice.startMicCapture();
      this.isListening = true;
      this.setState('listening');
      (this.micButton as HTMLElement).classList.add('active');
    } catch (e) {
      console.error('[CORTANA] Mic access denied:', e);
      this.setState('error');
      this.stateLabel.textContent = 'Mic access denied';
    }
  }

  private stopListening(): void {
    if (!this.isListening) return;
    this.isListening = false;
    this.voice.stopMicCapture();
    (this.micButton as HTMLElement).classList.remove('active');

    // For now, use text input as placeholder
    // In production, this would send audio data to backend for STT
    const text = this.transcript.textContent?.trim();
    if (text && text !== 'Say something...') {
      this.ws.sendTranscript(text);
    } else {
      this.setState('idle');
    }
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
      this.transcript.innerHTML = `<span class="assistant-text">${this.escapeHtml(this.currentResponse)}</span>`;
    } else if (msg.type === 'error') {
      this.transcript.innerHTML = `<span class="error-text">Error: ${this.escapeHtml(msg.message)}</span>`;
      this.setState('error');
    } else if (msg.type === 'history') {
      // Display conversation history
      const html = msg.messages
        .map((m: any) =>
          `<span class="${m.role}-text">${m.role === 'user' ? 'You: ' : 'CORTANA: '}${this.escapeHtml(m.content)}</span>`
        )
        .join('<br/>');
      this.transcript.innerHTML = html;
    }
  }

  private async onAudio(data: ArrayBuffer): Promise<void> {
    try {
      await this.voice.playAudio(data);
    } catch (e) {
      console.error('[CORTANA] Audio playback error:', e);
    }
  }

  private onWSOpen(): void {
    this.statusDot.classList.add('connected');
    this.setState('idle');
  }

  private onWSClose(): void {
    this.statusDot.classList.remove('connected');
  }

  private onWSError(): void {
    this.setState('error');
    this.stateLabel.textContent = 'Connection lost';
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
    <span>CORTANA</span>
  </div>
  <div id="orb-container"></div>
  <div id="state-label">Connecting...</div>
  <div id="transcript">Say something...</div>
  <button id="mic-button" title="Push to talk (Space)">🎤</button>
  <button id="settings-toggle" title="Settings">⚙</button>
  <div id="settings-panel"></div>
`;

// Initialize app
const app = new CortanaApp();

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  app.destroy();
});