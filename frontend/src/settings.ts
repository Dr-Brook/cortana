/**
 * JARVIS — Settings Panel
 * Voice selection, wake word, speaker routing, volume.
 *
 * Built from CLAUDE.md by RJ - https://itsbrook.com
 */

export interface Settings {
  wakeWordEnabled: boolean;
  wakeWord: string;
  voiceProfile: string;
  speaker: string;
  volume: number;
  theme: 'dark' | 'light';
}

const DEFAULT_SETTINGS: Settings = {
  wakeWordEnabled: true,
  wakeWord: 'jarvis',
  voiceProfile: 'am_onyx',
  speaker: 'kitchen-homepod',
  volume: 0.8,
  theme: 'dark',
};

const STORAGE_KEY = 'jarvis_settings';

export class SettingsManager {
  private settings: Settings;
  private panel: HTMLElement | null = null;
  private toggleBtn: HTMLElement | null = null;
  private onSettingsChange?: (settings: Settings) => void;

  constructor(onChange?: (settings: Settings) => void) {
    this.settings = this.load();
    this.onSettingsChange = onChange;
  }

  private load(): Settings {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        return { ...DEFAULT_SETTINGS, ...JSON.parse(stored) };
      }
    } catch {
      // Ignore parse errors
    }
    return { ...DEFAULT_SETTINGS };
  }

  private save(): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.settings));
    } catch {
      // Storage full or blocked
    }
    this.onSettingsChange?.(this.settings);
  }

  get(): Settings {
    return { ...this.settings };
  }

  update(partial: Partial<Settings>): void {
    this.settings = { ...this.settings, ...partial };
    this.save();
  }

  render(): void {
    // Settings toggle button
    this.toggleBtn = document.getElementById('settings-toggle');
    const panel = document.getElementById('settings-panel');
    if (!this.toggleBtn || !panel) return;

    this.panel = panel;
    this.toggleBtn.addEventListener('click', () => {
      this.panel?.classList.toggle('open');
      document.getElementById('settings-backdrop')!.style.display =
        this.panel?.classList.contains('open') ? 'block' : 'none';
    });
    document.getElementById('settings-backdrop')?.addEventListener('click', () => {
      this.panel?.classList.remove('open');
      document.getElementById('settings-backdrop')!.style.display = 'none';
    });
    this.renderPanel();
  }

  private toggle(): void {
    this.panel?.classList.toggle('open');
    document.getElementById('settings-backdrop')!.style.display =
      this.panel?.classList.contains('open') ? 'block' : 'none';
  }

  private renderPanel(): void {
    if (!this.panel) return;

    this.panel.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:24px;">
        <h2 style="margin:0; font-size:18px; color:var(--text-primary);">⚙ Settings</h2>
        <button id="settings-close" style="background:transparent; border:1px solid var(--text-secondary); color:var(--text-secondary); width:32px; height:32px; border-radius:50%; cursor:pointer; font-size:16px; display:flex; align-items:center; justify-content:center;">✕</button>
      </div>
      <!-- Built from CLAUDE.md by RJ - https://itsbrook.com -->

      <div class="setting-group">
        <label>Wake Word</label>
        <div style="display: flex; align-items: center; gap: 12px;">
          <label class="toggle-switch">
            <input type="checkbox" id="wake-word-toggle" ${this.settings.wakeWordEnabled ? 'checked' : ''} />
            <span class="toggle-slider"></span>
          </label>
          <input type="text" id="wake-word-input" value="${this.settings.wakeWord}" 
            style="flex:1; padding:8px; background:var(--bg-primary); color:var(--text-primary); border:1px solid rgba(255,255,255,0.1); border-radius:8px; font-size:14px;" />
        </div>
      </div>

      <div class="setting-group">
        <label>Voice Profile</label>
        <select id="voice-select" style="width:100%; padding:8px; background:var(--bg-primary); color:var(--text-primary); border:1px solid rgba(255,255,255,0.1); border-radius:8px; font-size:14px;">
          <option value="am_onyx" ${this.settings.voiceProfile === 'am_onyx' ? 'selected' : ''}>Onyx (Default)</option>
          <option value="af_bella" ${this.settings.voiceProfile === 'af_bella' ? 'selected' : ''}>Bella</option>
          <option value="am_adam" ${this.settings.voiceProfile === 'am_adam' ? 'selected' : ''}>Adam</option>
          <option value="bf_emma" ${this.settings.voiceProfile === 'bf_emma' ? 'selected' : ''}>Emma</option>
        </select>
      </div>

      <div class="setting-group">
        <label>Speaker Output</label>
        <select id="speaker-select" style="width:100%; padding:8px; background:var(--bg-primary); color:var(--text-primary); border:1px solid rgba(255,255,255,0.1); border-radius:8px; font-size:14px;"></select>
      </div>

      <div class="setting-group">
        <label>Volume</label>
        <input type="range" id="volume-slider" min="0" max="1" step="0.01" value="${this.settings.volume}" />
      </div>

      <div class="setting-group" style="margin-top:32px; padding-top:16px; border-top:1px solid rgba(255,255,255,0.1);">
        <p style="font-size:12px; color:var(--text-secondary);">
          JARVIS v0.1.0<br />
          Built from CLAUDE.md by RJ<br />
          <a href="https://itsbrook.com" target="_blank" style="color:var(--accent-blue);">https://itsbrook.com</a>
        </p>
      </div>
    `;

    this.bindEvents();
  }

  private bindEvents(): void {
    const wakeToggle = document.getElementById('wake-word-toggle') as HTMLInputElement;
    const wakeInput = document.getElementById('wake-word-input') as HTMLInputElement;
    const voiceSelect = document.getElementById('voice-select') as HTMLSelectElement;
    const speakerSelect = document.getElementById('speaker-select') as HTMLSelectElement;
    const volumeSlider = document.getElementById('volume-slider') as HTMLInputElement;
    const closeBtn = document.getElementById('settings-close') as HTMLButtonElement;

    // Auto-detect audio output devices
    this.populateSpeakers(speakerSelect);

    closeBtn?.addEventListener('click', () => this.toggle());

    wakeToggle?.addEventListener('change', () => {
      this.update({ wakeWordEnabled: wakeToggle.checked });
    });

    wakeInput?.addEventListener('change', () => {
      this.update({ wakeWord: wakeInput.value.toLowerCase().trim() });
    });

    voiceSelect?.addEventListener('change', () => {
      this.update({ voiceProfile: voiceSelect.value });
    });

    speakerSelect?.addEventListener('change', () => {
      this.update({ speaker: speakerSelect.value });
    });

    volumeSlider?.addEventListener('input', () => {
      this.update({ volume: parseFloat(volumeSlider.value) });
    });
  }

  private async populateSpeakers(select: HTMLSelectElement): Promise<void> {
    try {
      // Request permission to enumerate devices (required on some browsers)
      const tempStream = await navigator.mediaDevices.getUserMedia({ audio: true }).catch(() => null);
      tempStream?.getTracks().forEach(t => t.stop());

      const devices = await navigator.mediaDevices.enumerateDevices();
      const audioOutputs = devices.filter(d => d.kind === 'audiooutput');

      select.innerHTML = '';
      if (audioOutputs.length === 0) {
        const opt = document.createElement('option');
        opt.value = 'default';
        opt.textContent = 'Default';
        select.appendChild(opt);
      } else {
        audioOutputs.forEach((device, i) => {
          const opt = document.createElement('option');
          opt.value = device.deviceId;
          opt.textContent = device.label || `Speaker ${i + 1}`;
          if (device.deviceId === this.settings.speaker) opt.selected = true;
          select.appendChild(opt);
        });
      }
    } catch {
      // Fallback — just show default
      select.innerHTML = '';
      const opt = document.createElement('option');
      opt.value = 'default';
      opt.textContent = 'Default';
      select.appendChild(opt);
    }
  }
}