import test from 'node:test';
import assert from 'node:assert/strict';
import { buildLineage, compareCoverage, filterItems } from '../INTERFACE/sourceLineageModel.js';

const dynamic = {
  availability: { sources: [
    { asset: 'SAT/LIVE', type: 'IMAGE_COLLECTION', first_image_date: '2000-01-01', latest_image_date: '2026-08-01' },
    { asset: 'MAP/FIXED', type: 'IMAGE' },
  ] },
  families: [
    { family: 'pre', label: 'Precipitation', category: 'Climate', acquisition: 'Earth Engine', assets: ['SAT/LIVE'], used_period: '2000–2024', source: { name: 'Live satellite', asset: 'SAT/LIVE' } },
    { family: 'lka', label: 'Lake area', category: 'Hydrology', acquisition: 'Earth Engine', assets: ['MAP/FIXED'], used_period: 'fixed', source: { name: 'Fixed map', asset: 'MAP/FIXED' } },
    { family: 'ero', label: 'Erosion', category: 'Soils', acquisition: 'Not fetched', assets: [], used_period: 'Not fetched', source: { name: 'Erosion download', asset: 'EROSION' } },
  ],
};
const inventory = {
  rows: [{ id: 'rain', label: 'Rain', source: 'SAT/LIVE', coverage_to: '2024-12', status: 'available', group_id: 'climate' }],
  groups: [{ id: 'climate', label: 'Climate update', interval_days: 30, earth_engine: true, note: 'Append months' }],
};
const registry = { local_snapshots: [], external_sources: [{ id: 'paper', title: 'Gauge paper', classification: 'versioned_release', variables: ['discharge'] }] };

test('coverage comparison distinguishes an upstream update from an aligned record', () => {
  assert.equal(compareCoverage('2026-08-01', '2024-12'), 'source_newer');
  assert.equal(compareCoverage('2024-12-31', '2024-12'), 'aligned');
  assert.equal(compareCoverage(null, '2024-12'), 'unknown');
});

test('lineage separates live Earth Engine, direct downloads, research data and derived groups', () => {
  const model = buildLineage(dynamic, inventory, registry);
  assert.deepEqual(model.branches.map(branch => branch.id), ['earth_engine', 'local', 'downloads', 'external', 'derived']);
  assert.equal(model.counts.sourceNewer, 1);
  assert.equal(model.counts.continuing, 1);
  assert.equal(model.branches.find(branch => branch.id === 'downloads').items[0].title, 'Erosion download');
  assert.equal(model.branches.find(branch => branch.id === 'derived').items[0].variables[0].id, 'rain');
});

test('branch search includes variable names and respects temporal classification', () => {
  const model = buildLineage(dynamic, inventory, registry);
  assert.equal(filterItems(model.earthEngine, 'precipitation', 'all').length, 1);
  assert.equal(filterItems(model.earthEngine, '', 'fixed_reference').length, 0);
  assert.equal(filterItems(model.earthEngine, '', 'versioned_release').length, 1);
});
