/**
 * J.A.R.V.I.S. — Arc Reactor Three.js Visualization
 * Concentric rings, energy pulses, holographic feel — MCU Stark UI.
 *
 * Built from CLAUDE.md by RJ - https://itsbrook.com
 */

import * as THREE from 'three';

// MCU color palette — arc reactor blues/cyans
const ARC_COLORS: Record<string, THREE.Color> = {
  positive:  new THREE.Color(0x00ff88),  // arc green
  neutral:  new THREE.Color(0x00d4ff),   // arc blue
  negative: new THREE.Color(0xff3344),   // arc red
  thinking: new THREE.Color(0xffaa00),   // arc amber
  listening:new THREE.Color(0x00ff88),   // arc green
};

const RING_COUNT = 5;
const CORE_PARTICLES = 600;
const RING_SEGMENTS = 120;

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
  private container: HTMLElement;
  private animationId: number | null = null;
  private time: number = 0;

  // Core particles
  private corePoints!: THREE.Points;
  private corePositions: Float32Array;
  private coreVelocities: Float32Array;
  private coreBasePositions: Float32Array;
  private coreColors: Float32Array;

  // Rings
  private rings: THREE.Line[] = [];
  private ringData: { basePositions: Float32Array; radii: number[] }[] = [];

  // Outer glow particles
  private glowPoints!: THREE.Points;
  private glowPositions: Float32Array;
  private glowBasePositions: Float32Array;
  private glowColors: Float32Array;

  // Energy pulse ring
  private pulseRing!: THREE.Line;
  private pulseRadius: number = 0;
  private pulseAlpha: number = 0;

  // State
  private state: OrbState = {
    sentiment: 'neutral',
    energy: 0,
    isSpeaking: false,
    isListening: false,
  };

  private targetColor: THREE.Color;
  private currentColor: THREE.Color;

  constructor(containerId: string) {
    this.container = document.getElementById(containerId)!;
    this.targetColor = ARC_COLORS.neutral.clone();
    this.currentColor = ARC_COLORS.neutral.clone();

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

    // Build components
    this.corePositions = new Float32Array(CORE_PARTICLES * 3);
    this.coreVelocities = new Float32Array(CORE_PARTICLES * 3);
    this.coreBasePositions = new Float32Array(CORE_PARTICLES * 3);
    this.coreColors = new Float32Array(CORE_PARTICLES * 3);

    this.glowPositions = new Float32Array(CORE_PARTICLES * 3);
    this.glowBasePositions = new Float32Array(CORE_PARTICLES * 3);
    this.glowColors = new Float32Array(CORE_PARTICLES * 3);

    this.initCoreParticles();
    this.initRings();
    this.initGlowParticles();
    this.initPulseRing();
    this.initColors();

    // Handle resize
    window.addEventListener('resize', this.onResize.bind(this));

    // Start animation
    this.animate();
  }

  private initCoreParticles(): void {
    for (let i = 0; i < CORE_PARTICLES; i++) {
      // Inner sphere — dense core
      const phi = Math.acos(2 * Math.random() - 1);
      const theta = Math.random() * Math.PI * 2;
      const radius = 0.3 + Math.random() * 0.6;

      const x = radius * Math.sin(phi) * Math.cos(theta);
      const y = radius * Math.sin(phi) * Math.sin(theta);
      const z = radius * Math.cos(phi);

      const idx = i * 3;
      this.corePositions[idx] = x;
      this.corePositions[idx + 1] = y;
      this.corePositions[idx + 2] = z;
      this.coreBasePositions[idx] = x;
      this.coreBasePositions[idx + 1] = y;
      this.coreBasePositions[idx + 2] = z;

      this.coreVelocities[idx] = (Math.random() - 0.5) * 0.003;
      this.coreVelocities[idx + 1] = (Math.random() - 0.5) * 0.003;
      this.coreVelocities[idx + 2] = (Math.random() - 0.5) * 0.003;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(this.corePositions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(this.coreColors, 3));

    const material = new THREE.PointsMaterial({
      size: 0.035,
      vertexColors: true,
      transparent: true,
      opacity: 0.9,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });

    this.corePoints = new THREE.Points(geometry, material);
    this.scene.add(this.corePoints);
  }

  private initRings(): void {
    const ringRadii = [1.0, 1.4, 1.8, 2.2, 2.5];

    for (let r = 0; r < RING_COUNT; r++) {
      const radius = ringRadii[r];
      const positions = new Float32Array((RING_SEGMENTS + 1) * 3);
      const basePositions = new Float32Array((RING_SEGMENTS + 1) * 3);

      for (let s = 0; s <= RING_SEGMENTS; s++) {
        const angle = (s / RING_SEGMENTS) * Math.PI * 2;
        const idx = s * 3;
        const x = Math.cos(angle) * radius;
        const y = Math.sin(angle) * radius;
        positions[idx] = x;
        positions[idx + 1] = y;
        positions[idx + 2] = 0;
        basePositions[idx] = x;
        basePositions[idx + 1] = y;
        basePositions[idx + 2] = 0;
      }

      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

      // Inner rings brighter, outer rings dimmer
      const opacity = 0.15 + (0.2 * (1 - r / RING_COUNT));
      const material = new THREE.LineBasicMaterial({
        color: 0x00d4ff,
        transparent: true,
        opacity: opacity,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });

      const ring = new THREE.Line(geometry, material);
      this.scene.add(ring);
      this.rings.push(ring);
      this.ringData.push({ basePositions, radii: [radius] });
    }
  }

  private initGlowParticles(): void {
    // Outer glow particles — scattered around rings
    for (let i = 0; i < CORE_PARTICLES; i++) {
      const angle = Math.random() * Math.PI * 2;
      const ringIdx = Math.floor(Math.random() * RING_COUNT);
      const ringRadii = [1.0, 1.4, 1.8, 2.2, 2.5];
      const baseRadius = ringRadii[ringIdx] + (Math.random() - 0.5) * 0.15;

      const x = Math.cos(angle) * baseRadius;
      const y = Math.sin(angle) * baseRadius;
      const z = (Math.random() - 0.5) * 0.3;

      const idx = i * 3;
      this.glowPositions[idx] = x;
      this.glowPositions[idx + 1] = y;
      this.glowPositions[idx + 2] = z;
      this.glowBasePositions[idx] = x;
      this.glowBasePositions[idx + 1] = y;
      this.glowBasePositions[idx + 2] = z;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(this.glowPositions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(this.glowColors, 3));

    const material = new THREE.PointsMaterial({
      size: 0.02,
      vertexColors: true,
      transparent: true,
      opacity: 0.5,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });

    this.glowPoints = new THREE.Points(geometry, material);
    this.scene.add(this.glowPoints);
  }

  private initPulseRing(): void {
    const positions = new Float32Array(64 * 3);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const material = new THREE.LineBasicMaterial({
      color: 0x00d4ff,
      transparent: true,
      opacity: 0,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });

    this.pulseRing = new THREE.Line(geometry, material);
    this.scene.add(this.pulseRing);
  }

  private initColors(): void {
    const color = ARC_COLORS.neutral;
    for (let i = 0; i < CORE_PARTICLES; i++) {
      const idx = i * 3;
      this.coreColors[idx] = color.r;
      this.coreColors[idx + 1] = color.g;
      this.coreColors[idx + 2] = color.b;
      this.glowColors[idx] = color.r * 0.5;
      this.glowColors[idx + 1] = color.g * 0.5;
      this.glowColors[idx + 2] = color.b * 0.5;
    }
    this.corePoints.geometry.attributes.color.needsUpdate = true;
    this.glowPoints.geometry.attributes.color.needsUpdate = true;
  }

  setSentiment(sentiment: string): void {
    this.state.sentiment = sentiment;
    const target = ARC_COLORS[sentiment] || ARC_COLORS.neutral;
    this.targetColor.copy(target);
  }

  setEnergy(energy: number): void {
    this.state.energy = Math.max(0, Math.min(1, energy));
  }

  setSpeaking(speaking: boolean): void {
    this.state.isSpeaking = speaking;
    if (speaking) {
      this.pulseRadius = 0.5;
      this.pulseAlpha = 0.6;
    }
  }

  setListening(listening: boolean): void {
    this.state.isListening = listening;
  }

  private animate(): void {
    this.animationId = requestAnimationFrame(this.animate.bind(this));
    this.time += 0.016;

    // Lerp current color toward target
    this.currentColor.lerp(this.targetColor, 0.03);

    this.animateCore();
    this.animateRings();
    this.animateGlow();
    this.animatePulse();

    // Slow rotation for entire scene feel
    this.corePoints.rotation.z += 0.001;
    this.glowPoints.rotation.z -= 0.0005;

    this.renderer.render(this.scene, this.camera);
  }

  private animateCore(): void {
    const positions = this.corePoints.geometry.attributes.position as THREE.BufferAttribute;
    const colors = this.corePoints.geometry.attributes.color as THREE.BufferAttribute;

    for (let i = 0; i < CORE_PARTICLES; i++) {
      const idx = i * 3;

      // Breathing
      const breathe = Math.sin(this.time * 0.8 + i * 0.01) * 0.03;

      // Speaking: energetic pulse
      let speakPulse = 0;
      if (this.state.isSpeaking) {
        speakPulse = Math.sin(this.time * 10 + i * 0.04) * 0.2 * this.state.energy;
      }

      // Listening: gentle alert pulse
      let listenPulse = 0;
      if (this.state.isListening) {
        listenPulse = Math.sin(this.time * 3 + i * 0.02) * 0.1;
      }

      const totalOffset = breathe + speakPulse + listenPulse;
      const scale = 1 + totalOffset;

      this.corePositions[idx] = this.coreBasePositions[idx] * scale + this.coreVelocities[idx];
      this.corePositions[idx + 1] = this.coreBasePositions[idx + 1] * scale + this.coreVelocities[idx + 1];
      this.corePositions[idx + 2] = this.coreBasePositions[idx + 2] * scale + this.coreVelocities[idx + 2];

      // Dampen velocities
      this.coreVelocities[idx] *= 0.98;
      this.coreVelocities[idx + 1] *= 0.98;
      this.coreVelocities[idx + 2] *= 0.98;

      // Color — bright core with energy variation
      const brightness = 0.7 + totalOffset * 2.5;
      colors.array[idx] = this.currentColor.r * brightness;
      colors.array[idx + 1] = this.currentColor.g * brightness;
      colors.array[idx + 2] = this.currentColor.b * brightness;
    }

    positions.needsUpdate = true;
    colors.needsUpdate = true;
  }

  private animateRings(): void {
    for (let r = 0; r < this.rings.length; r++) {
      const ring = this.rings[r];
      const data = this.ringData[r];
      const positions = ring.geometry.attributes.position as THREE.BufferAttribute;
      const baseRadius = data.radii[0];

      // Each ring rotates at different speed
      const rotSpeed = (r % 2 === 0 ? 1 : -1) * (0.002 + r * 0.0005);
      ring.rotation.z += rotSpeed;

      // Slight tilt variation
      ring.rotation.x = Math.sin(this.time * 0.3 + r) * 0.15;
      ring.rotation.y = Math.cos(this.time * 0.2 + r * 0.5) * 0.1;

      // Animate ring vertex positions for breathing/pulse effect
      const energy = this.state.energy;
      for (let s = 0; s <= RING_SEGMENTS; s++) {
        const angle = (s / RING_SEGMENTS) * Math.PI * 2;
        const idx = s * 3;

        // Pulse effect — slight radius modulation
        let pulseMod = 1;
        if (this.state.isSpeaking) {
          pulseMod += Math.sin(this.time * 8 + angle * 3 + r) * 0.05 * energy;
        }
        if (this.state.isListening) {
          pulseMod += Math.sin(this.time * 4 + angle * 2) * 0.03;
        }

        const breathe = Math.sin(this.time * 0.5 + r * 0.7) * 0.02;
        const radius = (baseRadius + breathe) * pulseMod;

        positions.array[idx] = Math.cos(angle) * radius;
        positions.array[idx + 1] = Math.sin(angle) * radius;
        positions.array[idx + 2] = 0;
      }

      positions.needsUpdate = true;

      // Dynamic opacity — brighter when speaking
      const baseOpacity = 0.1 + (0.15 * (1 - r / this.rings.length));
      const speakOpacity = this.state.isSpeaking ? energy * 0.15 : 0;
      const listenOpacity = this.state.isListening ? 0.08 : 0;
      (ring.material as THREE.LineBasicMaterial).opacity = baseOpacity + speakOpacity + listenOpacity;

      // Update ring color to match sentiment
      (ring.material as THREE.LineBasicMaterial).color.lerp(this.currentColor, 0.03);
    }
  }

  private animateGlow(): void {
    const positions = this.glowPoints.geometry.attributes.position as THREE.BufferAttribute;
    const colors = this.glowPoints.geometry.attributes.color as THREE.BufferAttribute;

    for (let i = 0; i < CORE_PARTICLES; i++) {
      const idx = i * 3;

      // Gentle orbital movement
      const angle = this.time * 0.3 + i * 0.01;
      const wobble = Math.sin(this.time * 0.5 + i * 0.02) * 0.05;

      this.glowPositions[idx] = this.glowBasePositions[idx] * (1 + wobble);
      this.glowPositions[idx + 1] = this.glowBasePositions[idx + 1] * (1 + wobble);
      this.glowPositions[idx + 2] = this.glowBasePositions[idx + 2] + Math.sin(angle) * 0.02;

      const brightness = 0.3 + (this.state.isSpeaking ? this.state.energy * 0.5 : 0);
      colors.array[idx] = this.currentColor.r * brightness;
      colors.array[idx + 1] = this.currentColor.g * brightness;
      colors.array[idx + 2] = this.currentColor.b * brightness;
    }

    positions.needsUpdate = true;
    colors.needsUpdate = true;
  }

  private animatePulse(): void {
    // Expand pulse ring on speaking
    if (this.state.isSpeaking) {
      this.pulseRadius += 0.03;
      this.pulseAlpha -= 0.008;
      if (this.pulseAlpha <= 0) {
        this.pulseRadius = 0.5;
        this.pulseAlpha = 0.6;
      }
    } else {
      // Idle: subtle slow pulse
      this.pulseRadius = 2.8 + Math.sin(this.time * 0.5) * 0.2;
      this.pulseAlpha = 0.04 + Math.sin(this.time * 0.8) * 0.02;
    }

    const positions = this.pulseRing.geometry.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < 64; i++) {
      const angle = (i / 63) * Math.PI * 2;
      positions.array[i * 3] = Math.cos(angle) * this.pulseRadius;
      positions.array[i * 3 + 1] = Math.sin(angle) * this.pulseRadius;
      positions.array[i * 3 + 2] = 0;
    }
    positions.needsUpdate = true;

    (this.pulseRing.material as THREE.LineBasicMaterial).opacity = Math.max(0, this.pulseAlpha);
    (this.pulseRing.material as THREE.LineBasicMaterial).color.copy(this.currentColor);
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

    // Dispose all geometries and materials
    this.corePoints.geometry.dispose();
    (this.corePoints.material as THREE.Material).dispose();
    this.glowPoints.geometry.dispose();
    (this.glowPoints.material as THREE.Material).dispose();
    this.pulseRing.geometry.dispose();
    (this.pulseRing.material as THREE.Material).dispose();

    for (const ring of this.rings) {
      ring.geometry.dispose();
      (ring.material as THREE.Material).dispose();
    }

    window.removeEventListener('resize', this.onResize.bind(this));
  }
}