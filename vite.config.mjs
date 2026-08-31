import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const here = path => fileURLToPath(new URL(path, import.meta.url));

// The interface lives in INTERFACE/ and the browser-served files in PUBLISHED/,
// so Vite's root moves to INTERFACE. That keeps page URLs flat — /hydrography.html
// rather than /INTERFACE/hydrography.html — because Vite emits each HTML entry at
// its path relative to the root, and every page sits directly in it.
//
// Multi-page build: the portal SPA, the standalone hydrography explorer, the
// relationship tables that browse the stored graph, and the data catalogue that
// reads it back as an inventory.
// JSX is left to Vite's default esbuild transform, matching how the portal built before.
export default defineConfig({
  root: here('./INTERFACE'),
  publicDir: here('./PUBLISHED'),
  build: {
    outDir: here('./dist'),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: here('./INTERFACE/index.html'),
        hydrography: here('./INTERFACE/hydrography.html'),
        relationships: here('./INTERFACE/relationships.html'),
        catalogue: here('./INTERFACE/catalogue.html'),
        review: here('./INTERFACE/review.html'),
      },
    },
  },
});
