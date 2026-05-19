import { defineConfig } from 'vite';

// Built from CLAUDE.md by RJ - https://itsbrook.com

export default defineConfig({
  server: {
    port: 3002,
    host: true,
    allowedHosts: ['jarvis.100.89.58.6.nip.io', '10.0.0.157', 'localhost'],
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      external: ['openwakeword-wasm'],
    },
  },
});