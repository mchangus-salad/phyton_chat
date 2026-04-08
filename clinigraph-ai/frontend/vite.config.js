import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    // jsdom environment lets us render React components in Node with full DOM APIs.
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    // Glob that vitest uses to discover test files.
    include: ['src/**/*.{test,spec}.{js,jsx,ts,tsx}'],
    // Expose Jest-compatible expect globals so @testing-library/jest-dom matchers work.
    globals: true,
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Polling required for HMR to work on Windows host with Docker bind mounts.
    watch: {
      usePolling: true,
      interval: 300,
    },
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_API_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
        headers: { Host: 'localhost' },
      },
    },
  },
});
