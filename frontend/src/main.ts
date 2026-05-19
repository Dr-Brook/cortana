/**
 * J.A.R.V.I.S. — MCU Interface Controller
 * Startup sequence, HUD overlays, arc reactor state transitions.
 *
 * Built from CLAUDE.md by RJ - https://itsbrook.com
 */

import { JarvisOrb } from './orb';
import { WSClient, WS_BASE } from './ws';
import { VoicePipeline } from './voice';
import { SettingsManager } from './settings';
import { WakeWordDetector, WakeWordConfig } from './wakeword';
import './style.css';

type State = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

// ===== HUD Data Stream Messages =====
const HUD_MESSAGES = [
  'NEURAL LINK ACTIVE',
  'ARC REACTOR STABLE',
  'VOICE RECOGNITION ONLINE',
  'QUANTUM PROCESSOR NOMINAL',
  'DEFENSE MATRIX ONLINE',
  'BIOMETRIC SCAN CLEAR',
  'NEURAL INTERFACE SYNCED',
  'CORE TEMPERATURE NOMINAL',
  'DATA STREAM ENCRYPTED',
  'HUD CALIBRATION COMPLETE',
  'REACTOR OUTPUT 3.6 GJ/S',
  'FIREWALL INTEGRITY 100%',
  'SATELLITE UPLINK SECURED',
  'PATTERN RECOGNITION ACTIVE',
  'THREAT ASSESSMENT: NONE',
];

// ===== Startup Sequence =====
const STARTUP_LINES = [
  { text: 'INITIALIZING J.A.R.V.I.S. PROTOCOL', delay: 200 },
  { text: 'NEURAL INTERFACE BOOT', delay: 300, status: 'OK' },
  { text: 'ARC REACTOR CORE ONLINE', delay: 400, status: 'STABLE' },
  { text: 'VOICE RECOGNITION MODULE', delay: 300, status: 'ONLINE' },
  { text: 'QUANTUM PROCESSOR ARRAY', delay: 350, status: 'NOMINAL' },
  { text: 'HOLOGRAPHIC HUD CALIBRATION', delay: 400, status: 'COMPLETE' },
  { text: 'DEFENSE MATRIX INITIALIZATION', delay: 300, status: 'ACTIVE' },
  { text: 'CONNECTING TO NEURAL LINK', delay: 500 },
];

class JarvisApp {
  private state: State = 'idle';
  private orb: JarvisOrb;
  private ws: WSClient;
  private voice: VoicePipeline;
  private settings: SettingsManager;
  private wakeWord: WakeWordDetector | null = null;
  private stateLabel: HTMLElement;
  private transcript: HTMLElement;
  private micButton: HTMLElement;
  private statusDot: HTMLElement;
  private isListening = false;
  private currentResponse = '';

  // HUD elements
  private hudLeft: HTMLElement;
  private hudRight: HTMLElement;
  private hudBottom: HTMLElement;
  private hudDataStreamInterval: ReturnType<typeof setInterval> | null = null;
  private hudTimeInterval: ReturnType<typeof setInterval> | null = null;

  // Weather data
  private weatherData: { temp: string; short: string; wind: string; precip: string } | null = null;
  private weatherFetchInterval: ReturnType<typeof setInterval> | null = null;

  // News data
  private newsArticles: { title: string; source: string; url: string; published: string; desc: string }[] = [];
  private newsIndex = 0;
  private newsFetchInterval: ReturnType<typeof setInterval> | null = null;
  private newsAutoInterval: ReturnType<typeof setInterval> | null = null;

  // Startup
  private startupComplete = false;

  constructor() {
    // Initialize UI elements
    this.stateLabel = document.getElementById('state-label')!;
    this.transcript = document.getElementById('transcript')!;
    this.micButton = document.getElementById('mic-button')!;
    this.statusDot = document.querySelector('#connection-status .dot')!;
    this.hudLeft = document.getElementById('hud-left')!;
    this.hudRight = document.getElementById('hud-right')!;
    this.hudBottom = document.getElementById('hud-bottom')!;

    // Show WS URL on startup
    this.stateLabel.textContent = 'CONNECTING...';

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

    // Run startup sequence
    this.runStartupSequence();

    // Initialize wake word detector
    this._initWakeWord();

    // Connect
    this.ws.connect();
  }

  // ===== Startup Sequence =====

  private async runStartupSequence(): Promise<void> {
    const startupScreen = document.getElementById('startup-screen')!;
    const startupLog = document.getElementById('startup-log')!;

    for (const line of STARTUP_LINES) {
      await this.delay(line.delay);
      const lineEl = document.createElement('div');
      lineEl.className = 'log-line';
      if (line.status) {
        lineEl.innerHTML = `<span class="log-prefix">▸</span> ${line.text} <span class="log-${line.status === 'OK' || line.status === 'ONLINE' || line.status === 'NOMINAL' || line.status === 'ACTIVE' || line.status === 'COMPLETE' || line.status === 'STABLE' ? 'ok' : 'status'}">${line.status}</span>`;
      } else {
        lineEl.innerHTML = `<span class="log-prefix">▸</span> ${line.text}...`;
      }
      startupLog.appendChild(lineEl);
    }

    await this.delay(600);

    // Fade out startup screen
    startupScreen.classList.add('fade-out');
    await this.delay(800);
    startupScreen.remove();

    this.startupComplete = true;

    // Show HUD elements
    this.hudLeft.classList.add('visible');
    this.hudRight.classList.add('visible');
    this.hudBottom.classList.add('visible');

    // Show news panel after startup
    setTimeout(() => {
      document.getElementById('news-panel')?.classList.add('visible');
    }, 8000);

    // Start HUD data streams
    this.startHUDStreams();

    // Fetch weather and refresh every 30 minutes
    this.fetchWeather();
    this.weatherFetchInterval = setInterval(() => this.fetchWeather(), 30 * 60 * 1000);

    // Fetch news and refresh every 15 minutes
    this.fetchNews();
    this.setupNewsNav();
    this.newsFetchInterval = setInterval(() => this.fetchNews(), 15 * 60 * 1000);
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  // ===== HUD Streams =====

  private startHUDStreams(): void {
    // Left panel — system status
    this.updateHUDLeft();

    // Right panel — time/date
    this.updateHUDRight();

    // Bottom data stream — cycling messages
    let msgIndex = 0;
    this.hudBottom.textContent = HUD_MESSAGES[0];
    this.hudDataStreamInterval = setInterval(() => {
      msgIndex = (msgIndex + 1) % HUD_MESSAGES.length;
      this.hudBottom.textContent = HUD_MESSAGES[msgIndex];
    }, 3000);

    // Update time every second
    this.hudTimeInterval = setInterval(() => {
      this.updateHUDRight();
    }, 1000);
  }

  private updateHUDLeft(): void {
    const wsStatus = this.statusDot.classList.contains('connected') ? 'ONLINE' : 'OFFLINE';
    const wsClass = this.statusDot.classList.contains('connected') ? 'online' : 'offline';
    const stateText = this.state.toUpperCase();

    this.hudLeft.innerHTML = `
      <div class="hud-status-line">
        <span class="hud-dot green"></span>
        <span class="hud-label">NEURAL LINK</span>
        <span class="hud-value ${wsClass}">${wsStatus}</span>
      </div>
      <div class="hud-status-line">
        <span class="hud-dot"></span>
        <span class="hud-label">STATUS</span>
        <span class="hud-value">${stateText}</span>
      </div>
      <div class="hud-status-line">
        <span class="hud-dot green"></span>
        <span class="hud-label">CORE</span>
        <span class="hud-value online">STABLE</span>
      </div>
      <div class="hud-status-line">
        <span class="hud-dot"></span>
        <span class="hud-label">FREQ</span>
        <span class="hud-value">440.0 HZ</span>
      </div>
    `;
  }

  private async fetchWeather(): Promise<void> {
    try {
      // Build the weather API URL from the current page location
      const proto = window.location.protocol === 'https:' ? 'https:' : 'http:';
      const host = window.location.host;
      // If accessing via Caddy proxy (no port or standard port), use same origin
      // If direct access (port 3002), point to backend port 8444
      const isDirect = window.location.port === '3002' || window.location.port === '5173';
      const weatherUrl = isDirect
        ? `http://${window.location.hostname}:8444/weather`
        : `${proto}//${host}/weather`;
      const resp = await fetch(weatherUrl);
      if (resp.ok) {
        const data = await resp.json();
        if (data.forecast && data.forecast.length > 0) {
          const current = data.forecast[0];
          this.weatherData = {
            temp: current.temperature,
            short: current.short,
            wind: current.wind,
            precip: current.precip,
          };
        }
      }
    } catch {
      // Weather unavailable — HUD will show dashes
    }
  }

  private async fetchNews(): Promise<void> {
    try {
      const isDirect = window.location.port === '3002' || window.location.port === '5173';
      const newsUrl = isDirect
        ? `http://${window.location.hostname}:8444/news`
        : `${window.location.protocol}//${window.location.host}/news`;
      const resp = await fetch(newsUrl);
      if (resp.ok) {
        const data = await resp.json();
        if (data.articles && data.articles.length > 0) {
          this.newsArticles = data.articles;
          this.newsIndex = 0;
          this.renderNewsCard();
        }
      }
    } catch {
      const el = document.getElementById('news-loading');
      if (el) el.textContent = 'DATASTREAM OFFLINE';
    }
  }

  private renderNewsCard(): void {
    const container = document.getElementById('news-cards');
    const counter = document.getElementById('news-counter');
    if (!container || this.newsArticles.length === 0) return;

    const article = this.newsArticles[this.newsIndex];
    const idx = this.newsIndex + 1;
    const total = this.newsArticles.length;
    if (counter) counter.textContent = `${idx}/${total}`;

    container.innerHTML = `
      <div class="news-card">
        <div class="news-title">${this.escapeHtml(article.title)}</div>
        <div class="news-meta">${this.escapeHtml(article.source)} · ${this.escapeHtml(article.published)}</div>
        <div class="news-desc">${this.escapeHtml(article.desc)}</div>
      </div>
    `;
  }

  private setupNewsNav(): void {
    document.getElementById('news-prev')?.addEventListener('click', () => {
      if (this.newsArticles.length === 0) return;
      this.newsIndex = (this.newsIndex - 1 + this.newsArticles.length) % this.newsArticles.length;
      this.renderNewsCard();
    });
    document.getElementById('news-next')?.addEventListener('click', () => {
      if (this.newsArticles.length === 0) return;
      this.newsIndex = (this.newsIndex + 1) % this.newsArticles.length;
      this.renderNewsCard();
    });

    // Auto-advance every 8 seconds
    this.newsAutoInterval = setInterval(() => {
      if (this.newsArticles.length > 0) {
        this.newsIndex = (this.newsIndex + 1) % this.newsArticles.length;
        this.renderNewsCard();
      }
    }, 8000);
  }

  private updateHUDRight(): void {
    const now = new Date();
    const time = now.toLocaleTimeString('en-US', { hour12: false });
    const date = now.toLocaleDateString('en-US', { year: '2-digit', month: '2-digit', day: '2-digit' });
    const day = now.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();

    const wTemp = this.weatherData?.temp ?? '——';
    const wShort = this.weatherData?.short ?? '——';
    const wWind = this.weatherData?.wind ?? '——';
    const wPrecip = this.weatherData?.precip ?? '——';

    this.hudRight.innerHTML = `
      <div class="hud-status-line">
        <span class="hud-value">${time}</span>
      </div>
      <div class="hud-status-line">
        <span class="hud-value">${date}</span>
      </div>
      <div class="hud-status-line">
        <span class="hud-value">${day}</span>
      </div>
      <div class="hud-divider"></div>
      <div class="hud-status-line">
        <span class="hud-dot cyan"></span>
        <span class="hud-label">WEATHER</span>
      </div>
      <div class="hud-status-line">
        <span class="hud-label">TEMP</span>
        <span class="hud-value cyan">${wTemp}</span>
      </div>
      <div class="hud-status-line">
        <span class="hud-label">COND</span>
        <span class="hud-value cyan">${wShort}</span>
      </div>
      <div class="hud-status-line">
        <span class="hud-label">WIND</span>
        <span class="hud-value">${wWind}</span>
      </div>
      <div class="hud-status-line">
        <span class="hud-label">RAIN</span>
        <span class="hud-value">${wPrecip}</span>
      </div>
      <div class="hud-status-line" style="margin-top:6px;">
        <span class="hud-label">LAT 35.22N</span>
      </div>
      <div class="hud-status-line">
        <span class="hud-label">LON 80.84W</span>
      </div>
    `;
  }

  // ===== UI Setup =====

  private setupUI(): void {
    // Mic button — tap to dictate
    this.micButton.addEventListener('click', () => {
      // Unlock AudioContext on user gesture (iOS Safari)
      if (this.voice['audioContext']?.state === 'suspended') {
        this.voice['audioContext'].resume();
      }
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
    this.updateHUDLeft();

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
      idle: 'STANDBY',
      listening: 'LISTENING',
      thinking: 'PROCESSING',
      speaking: 'TRANSMITTING',
      error: 'SYSTEM ERROR',
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

    // Priority: Web Speech API dictation first (instant text → fast response)
    if (VoicePipeline.hasDictation()) {
      this.startDictation();
      return;
    }

    // Fallback: backend Whisper STT (slower, requires round-trip)
    if (VoicePipeline.hasBackendSTT()) {
      this.isListening = true;
      this.setState('listening');
      (this.micButton as HTMLElement).classList.add('active');

      // Start audio stream
      this.ws.startAudioStream();

      let chunkCount = 0;
      await this.voice.startBackendSTT(
        (data) => {
          if (this.state === 'speaking') return;
          this.ws.sendAudioChunk(data);
          chunkCount++;
        },
        (level) => {
          this.orb.setEnergy(Math.max(0.2, level));
        },
        (err) => {
          console.error('[JARVIS] Backend STT error:', err);
          this.isListening = false;
          (this.micButton as HTMLElement).classList.remove('active');
          this.setState('idle');
          this.transcript.innerHTML = '<span class="error-text">VOICE INPUT FAILED — TYPE BELOW</span>';
        }
      );

      this.transcript.innerHTML = '<span class="user-text">LISTENING...</span>';
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
      this.setState('error');
      this.transcript.innerHTML = '<span class="error-text">MICROPHONE ACCESS DENIED</span>';
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
          this.transcript.innerHTML = `<span class="user-text">${this.escapeHtml(finalText ? finalText + ' ' + text : text)}_</span>`;
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
        this.transcript.innerHTML = '';
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
    // Don't override speaking while audio is playing
    if (this.state === 'speaking' && (state === 'idle' || state === 'thinking') && this.voice.playing) {
      return;
    }
    // Don't override thinking while waiting for LM response
    if (this.state === 'thinking' && state === 'idle') {
      return;
    }
    this.setState(state as State);
    if (sentiment) {
      this.orb.setSentiment(sentiment);
    }
  }

  private onMessage(msg: any): void {
    if (msg.type === 'text_chunk') {
      this.currentResponse += msg.text;
    } else if (msg.type === 'error') {
      this.transcript.innerHTML = `<span class="error-text">${this.escapeHtml(msg.message)}</span>`;
      this.setState('error');
    } else if (msg.type === 'history') {
      // No-op
    }
  }

  private async onAudio(data: ArrayBuffer): Promise<void> {
    try {
      await this.voice.playAudio(data);
      // Audio finished playing — now safe to go idle if server already sent idle
      if (this.state === 'speaking') {
        this.setState('idle');
      }
    } catch (e) {
      console.error('[JARVIS] Audio playback error:', e);
    }
  }

  private onWSOpen(): void {
    this.statusDot.classList.add('connected');
    this.setState('idle');
    this.transcript.innerHTML = '';
    this.updateHUDLeft();
  }

  private onWSClose(): void {
    this.statusDot.classList.remove('connected');
    this.updateHUDLeft();
  }

  private onWSError(): void {
    this.setState('error');
    this.stateLabel.textContent = 'LINK LOST';
    this.updateHUDLeft();
  }

  // ---- Settings ----

  private onSettingsChange(settings: any): void {
    this.voice.setVolume(settings.volume);
  }

  // ---- Wake Word ----

  private async _initWakeWord(): Promise<void> {
    const supported = await WakeWordDetector.isSupported();
    if (!supported) {
      console.info('[JARVIS] Wake word detection not available');
      return;
    }

    this.wakeWord = new WakeWordDetector({
      enabled: true,
      word: 'hey_jarvis',
      sensitivity: 0.5,
    });

    this.wakeWord.start(
      () => {
        // Wake word detected — start listening
        console.log('[JARVIS] Wake word detected!');
        this.startListening();
      },
      (level) => {
        // Update orb idle energy with wake word mic level
        if (this.state === 'idle') {
          this.orb.setEnergy(Math.max(0.05, level * 0.5));
        }
      }
    );
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
    if (this.wakeWord) {
      this.wakeWord.stop();
      this.wakeWord = null;
    }
    if (this.hudDataStreamInterval) clearInterval(this.hudDataStreamInterval);
    if (this.hudTimeInterval) clearInterval(this.hudTimeInterval);
    if (this.weatherFetchInterval) clearInterval(this.weatherFetchInterval);
    if (this.newsFetchInterval) clearInterval(this.newsFetchInterval);
    if (this.newsAutoInterval) clearInterval(this.newsAutoInterval);
  }
}

// ---- Bootstrap ----
const appContainer = document.getElementById('app')!;

// Create UI structure — MCU HUD layout
appContainer.innerHTML = `
  <!-- Startup Screen -->
  <div id="startup-screen">
    <div id="startup-title">J.A.R.V.I.S.</div>
    <div id="startup-log"></div>
  </div>

  <!-- Scan Line Overlay -->
  <div id="scan-overlay"></div>

  <!-- HUD Corner Brackets -->
  <div class="hud-corner hud-corner-tl"></div>
  <div class="hud-corner hud-corner-tr"></div>
  <div class="hud-corner hud-corner-bl"></div>
  <div class="hud-corner hud-corner-br"></div>

  <!-- HUD Left Panel — System Status -->
  <div id="hud-left"></div>

  <!-- HUD Right Panel — Time/Date -->
  <div id="hud-right"></div>

  <!-- HUD Bottom — Data Stream -->
  <div id="hud-bottom"></div>

  <!-- News Feed Panel -->
  <div id="news-panel">
    <div id="news-header">
      <span class="hud-dot cyan"></span>
      <span class="hud-label">INTEL FEED</span>
      <span id="news-category" class="hud-value cyan">GENERAL</span>
    </div>
    <div id="news-cards">
      <div id="news-loading">SCANNING DATASTREAMS...</div>
    </div>
    <div id="news-nav">
      <button id="news-prev" title="Previous">◂</button>
      <span id="news-counter">0/0</span>
      <button id="news-next" title="Next">▸</button>
    </div>
  </div>

  <!-- Connection Status -->
  <div id="connection-status">
    <span class="dot"></span>
    <span>NEURAL LINK</span>
  </div>

  <!-- Arc Reactor Orb -->
  <div id="orb-container"></div>
  <div id="state-label">INITIALIZING</div>
  <div id="transcript"></div>

  <!-- Mic Button -->
  <button id="mic-button" title="PUSH TO TALK [SPACE]">🎤</button>

  <!-- Text Input -->
  <div id="text-input-container">
    <input id="text-input" type="text" placeholder="ENTER COMMAND..." />
    <button id="send-button">SEND</button>
  </div>

  <!-- Settings -->
  <div id="settings-backdrop"></div>
  <button id="settings-toggle" title="Settings">⚙</button>
  <div id="settings-panel"></div>
`;

// Initialize app
const app = new JarvisApp();

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  app.destroy();
});