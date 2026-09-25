import { fileURLToPath } from 'node:url';
import { createReadStream, statSync } from 'node:fs';
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
  plugins: [{
    name: 'raw-catchment-matrices',
    // These are hashed application payloads, not HTTP-compressed responses.
    // Vite's static middleware otherwise labels .gz as Content-Encoding: gzip.
    configureServer(server) { server.middlewares.use(rawMatrices(here('./PUBLISHED'))); },
    configurePreviewServer(server) { server.middlewares.use(rawMatrices(here('./dist'))); },
  }],
  base: process.env.SITE_BASE || '/',
  root: here('./INTERFACE'),
  publicDir: process.env.LAUNCH_BUILD ? false : here('./PUBLISHED'),
  build: {
    outDir: here('./dist'),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: here('./INTERFACE/index.html'),
        admin: here('./INTERFACE/admin.html'),
        project: here('./INTERFACE/project.html'),
        examples: here('./INTERFACE/examples.html'),
        ...(process.env.LAUNCH_BUILD ? {} : { portal: here('./INTERFACE/portal.html') }),
        metadata: here('./INTERFACE/metadata.html'),
        atlas: here('./INTERFACE/atlas.html'),
        roadmap: here('./INTERFACE/roadmap.html'),
        surrogates: here('./INTERFACE/surrogates.html'),
        dynamicAtlas: here('./INTERFACE/dynamic-atlas.html'),
        dataLineage: here('./INTERFACE/data-lineage.html'),
        hydrography: here('./INTERFACE/hydrography.html'),
        landcover: here('./INTERFACE/landcover.html'),
        climate: here('./INTERFACE/climate.html'),
        caseStudies: here('./INTERFACE/case-studies.html'),
        waterFlow: here('./INTERFACE/water-flow.html'),
        trends: here('./INTERFACE/trends.html'),
        ontology: here('./INTERFACE/ontology.html'),
        relationships: here('./INTERFACE/relationships.html'),
        catalogue: here('./INTERFACE/catalogue.html'),
        review: here('./INTERFACE/review.html'),
        about: here('./INTERFACE/about.html'),
        guide: here('./INTERFACE/guide.html'),
        projects: here('./INTERFACE/projects.html'),
        research: here('./INTERFACE/research.html'),
        drySpell: here('./INTERFACE/dry-spell.html'),
        drought: here('./INTERFACE/drought.html'),
        reservoirMonitoring: here('./INTERFACE/reservoir-monitoring.html'),
      },
    },
  },
});

function rawMatrices(root) {
  return (request, response, next) => {
    const pathname = request.url?.split('?')[0];
    if (!/^\/data\/atlas\/catchments\/[a-z0-9_-]+\.bin\.gz$/.test(pathname || '')
      || !['GET', 'HEAD'].includes(request.method)) return next();
    const filename = `${root}${pathname}`;
    let stat;
    try { stat = statSync(filename); } catch { return next(); }
    response.setHeader('Content-Type', 'application/gzip');
    response.setHeader('Content-Length', stat.size);
    response.setHeader('Cache-Control', 'no-cache');
    if (request.method === 'HEAD') return response.end();
    createReadStream(filename).on('error', error => response.destroy(error)).pipe(response);
  };
}
