import { defineConfig } from 'vite';
import { resolve } from 'node:path';
import { forgeApi } from './tools/viewer-api';

export default defineConfig({
  plugins: [forgeApi()],
  resolve: {
    alias: {
      '@core/brush': resolve(__dirname, 'core/brush/index.ts'),
      '@core/pixel': resolve(__dirname, 'core/pixel.ts'),
      '@core': resolve(__dirname, 'core/index.ts'),
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        viewer: resolve(__dirname, 'viewer/index.html'),
      },
    },
  },
  // Fixed port: if 5173 is taken, fail with a clear error instead of silently serving elsewhere.
  server: {
    port: 5173,
    strictPort: true,
    open: false,
    // Local only: the viewer and sandboxes are not reachable from other machines on the network.
    host: '127.0.0.1',
    hmr: false,
  },
});
