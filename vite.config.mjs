import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

// Multi-page build: the portal SPA plus the standalone hydrography explorer.
// JSX is left to Vite's default esbuild transform, matching how the portal built before.
export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        hydrography: fileURLToPath(new URL('./hydrography.html', import.meta.url)),
      },
    },
  },
});
