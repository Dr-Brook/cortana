import { defineConfig } from 'vite';

// Built from CLAUDE.md by RJ - https://itsbrook.com

export default defineConfig({
  server: {
    port: 3002,
    host: true,
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      external: ['openwakeword-wasm'],
    },
  },
});