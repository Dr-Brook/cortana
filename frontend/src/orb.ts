/**
 * JARVIS — Three.js Particle Orb
 * Audio-reactive particle system with sentiment-based color shifts.
 *
 * Built from CLAUDE.md by RJ - https://itsbrook.com
 */

import * as THREE from 'three';

// Sentiment color map
const SENTIMENT_COLORS: Record<string, THREE.Color> = {
  positive: new THREE.Color(0x4caf50),  // green
  neutral: new THREE.Color(0x4a90d9),   // blue
  negative: new THREE.Color(0xef5350),  // red
  thinking: new THREE.Color(0xffc107),   // yellow
  listening: new THREE.Color(0x4caf50), // green
};

const PARTICLE_COUNT = 1500;
const BASE_RADIUS = 2.0;

interface OrbState {
  sentiment: string;
  energy: number;
  isSpeaking: boolean;
  isListening: boolean;
}

export class JarvisOrb {
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer;
  private particles: THREE.Points;
  private positions: Float32Array;
  private velocities: Float32Array;
  private basePositions: Float32Array;
  private colors: Float32Array;
  private targetColor: THREE.Color;
  private currentColor: THREE.Color;
  private container: HTMLElement;
  private animationId: number | null = null;
  private time: number = 0;
  private state: OrbState = {
    sentiment: 'neutral',
    energy: 0,
    isSpeaking: false,
    isListening: false,
  };

  constructor(containerId: string) {
    this.container = document.getElementById(containerId)!;
    this.targetColor = SENTIMENT_COLORS.neutral.clone();
    this.currentColor = SENTIMENT_COLORS.neutral.clone();

    // Scene setup
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(
      45,
      this.container.clientWidth / this.container.clientHeight,
      0.1,
      100
    );
    this.camera.position.z = 6;

    this.renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
    });
    this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.container.appendChild(this.renderer.domElement);

    // Create particles
    const geometry = new THREE.BufferGeometry();
    this.positions = new Float32Array(PARTICLE_COUNT * 3);
    this.velocities = new Float32Array(PARTICLE_COUNT * 3);
    this.basePositions = new Float32Array(PARTICLE_COUNT * 3);
    this.colors = new Float32Array(PARTICLE_COUNT * 3);

    this.initParticles();

    geometry.setAttribute('position', new THREE.BufferAttribute(this.positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(this.colors, 3));

    const material = new THREE.PointsMaterial({
      size: 0.04,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });

    this.particles = new THREE.Points(geometry, material);
    this.scene.add(this.particles);

    // Now init colors — needs this.particles to exist
    this.initColors();

    // Handle resize
    window.addEventListener('resize', this.onResize.bind(this));

    // Start animation
    this.animate();
  }

  private initParticles(): void {
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      // Distribute on sphere surface with some randomness
      const phi = Math.acos(2 * Math.random() - 1);
      const theta = Math.random() * Math.PI * 2;
      const radius = BASE_RADIUS + (Math.random() - 0.5) * 0.5;

      const x = radius * Math.sin(phi) * Math.cos(theta);
      const y = radius * Math.sin(phi) * Math.sin(theta);
      const z = radius * Math.cos(phi);

      const idx = i * 3;
      this.positions[idx] = x;
      this.positions[idx + 1] = y;
      this.positions[idx + 2] = z;

      this.basePositions[idx] = x;
      this.basePositions[idx + 1] = y;
      this.basePositions[idx + 2] = z;

      // Small random velocities
      this.velocities[idx] = (Math.random() - 0.5) * 0.002;
      this.velocities[idx + 1] = (Math.random() - 0.5) * 0.002;
      this.velocities[idx + 2] = (Math.random() - 0.5) * 0.002;
    }
  }

  private initColors(): void {
    const color = SENTIMENT_COLORS.neutral;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const idx = i * 3;
      this.colors[idx] = color.r;
      this.colors[idx + 1] = color.g;
      this.colors[idx + 2] = color.b;
    }
    this.particles.geometry.attributes.color.needsUpdate = true;
  }

  setSentiment(sentiment: string): void {
    this.state.sentiment = sentiment;
    const target = SENTIMENT_COLORS[sentiment] || SENTIMENT_COLORS.neutral;
    this.targetColor.copy(target);
  }

  setEnergy(energy: number): void {
    this.state.energy = Math.max(0, Math.min(1, energy));
  }

  setSpeaking(speaking: boolean): void {
    this.state.isSpeaking = speaking;
  }

  setListening(listening: boolean): void {
    this.state.isListening = listening;
  }

  private animate(): void {
    this.animationId = requestAnimationFrame(this.animate.bind(this));
    this.time += 0.016; // ~60fps

    // Lerp current color toward target
    this.currentColor.lerp(this.targetColor, 0.02);

    const positions = this.particles.geometry.attributes.position as THREE.BufferAttribute;
    const colors = this.particles.geometry.attributes.color as THREE.BufferAttribute;

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const idx = i * 3;

      // Breathing animation (idle)
      const breathe = Math.sin(this.time * 0.5 + i * 0.01) * 0.02;

      // Speaking: energetic pulse
      let speakPulse = 0;
      if (this.state.isSpeaking) {
        speakPulse = Math.sin(this.time * 8 + i * 0.05) * 0.15 * this.state.energy;
      }

      // Listening: bright alert
      let listenPulse = 0;
      if (this.state.isListening) {
        listenPulse = Math.sin(this.time * 4 + i * 0.03) * 0.08;
      }

      // Combine animations
      const totalOffset = breathe + speakPulse + listenPulse;
      const scale = 1 + totalOffset;

      // Apply to positions
      this.positions[idx] = this.basePositions[idx] * scale + this.velocities[idx];
      this.positions[idx + 1] = this.basePositions[idx + 1] * scale + this.velocities[idx + 1];
      this.positions[idx + 2] = this.basePositions[idx + 2] * scale + this.velocities[idx + 2];

      // Dampen velocities
      this.velocities[idx] *= 0.99;
      this.velocities[idx + 1] *= 0.99;
      this.velocities[idx + 2] *= 0.99;

      // Update colors
      const brightness = 0.6 + totalOffset * 2;
      colors.array[idx] = this.currentColor.r * brightness;
      colors.array[idx + 1] = this.currentColor.g * brightness;
      colors.array[idx + 2] = this.currentColor.b * brightness;
    }

    positions.needsUpdate = true;
    colors.needsUpdate = true;

    // Slow rotation
    this.particles.rotation.y += 0.002;
    this.particles.rotation.x += 0.001;

    this.renderer.render(this.scene, this.camera);
  }

  private onResize(): void {
    if (!this.container) return;
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  destroy(): void {
    if (this.animationId !== null) {
      cancelAnimationFrame(this.animationId);
    }
    this.renderer.dispose();
    this.particles.geometry.dispose();
    (this.particles.material as THREE.Material).dispose();
    window.removeEventListener('resize', this.onResize.bind(this));
  }
}