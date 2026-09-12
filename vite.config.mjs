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
  base: process.env.SITE_BASE || '/',
  root: here('./INTERFACE'),
  publicDir: process.env.LAUNCH_BUILD ? false : here('./PUBLISHED'),
  build: {
    outDir: here('./dist'),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: here('./INTERFACE/index.html'),
        ...(process.env.LAUNCH_BUILD ? {} : { portal: here('./INTERFACE/portal.html') }),
        metadata: here('./INTERFACE/metadata.html'),
        atlas: here('./INTERFACE/atlas.html'),
        roadmap: here('./INTERFACE/roadmap.html'),
        surrogates: here('./INTERFACE/surrogates.html'),
        dynamicAtlas: here('./INTERFACE/dynamic-atlas.html'),
        hydrography: here('./INTERFACE/hydrography.html'),
        landcover: here('./INTERFACE/landcover.html'),
        climate: here('./INTERFACE/climate.html'),
        caseStudies: here('./INTERFACE/case-studies.html'),
        ontology: here('./INTERFACE/ontology.html'),
        relationships: here('./INTERFACE/relationships.html'),
        catalogue: here('./INTERFACE/catalogue.html'),
        review: here('./INTERFACE/review.html'),
        about: here('./INTERFACE/about.html'),
        guide: here('./INTERFACE/guide.html'),
        projects: here('./INTERFACE/projects.html'),
      },
    },
  },
});
