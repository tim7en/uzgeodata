import test from 'node:test';
import assert from 'node:assert/strict';
import {overlayFeatureCollection, temporalSeriesCsv} from '../INTERFACE/ontologyExportModel.js';

test('temporal CSV carries entity, geography, raw value and deviation context', () => {
  const csv = temporalSeriesCsv({
    entityType: 'basin', entityId: '462172411000', basin12: '4120396550',
    basin7: '4070396550', districts: 'Bostanlik', province: 'Tashkent',
    dataset: 'uz:ds/cfsv2-noaa', variable: 'soil_moisture_25cm', unit: 'm3/m3',
  }, [{period: '2026-08', value: .25, z: -.4, classification: 'normal'}]);
  assert.match(csv, /entity_type,entity_id,basin_l12/);
  assert.match(csv, /basin,462172411000,4120396550,4070396550,Bostanlik,Tashkent/);
  assert.match(csv, /2026-08,0.25,-0.4,normal/);
});

test('overlay export remains a valid mixed-geometry GeoJSON FeatureCollection', () => {
  const overlay = overlayFeatureCollection([
    {type: 'Feature', properties: {ENTITY: 'reach'}, geometry: {type: 'LineString', coordinates: [[1, 2], [2, 3]]}},
    {type: 'Feature', properties: {ENTITY: 'basin'}, geometry: {type: 'Polygon', coordinates: [[[1, 2], [2, 2], [1, 2]]]}},
  ], {name: 'trace', variable: 'precipitation'});
  assert.equal(overlay.type, 'FeatureCollection');
  assert.equal(overlay.features.length, 2);
  assert.deepEqual(overlay.features.map(feature => feature.geometry.type), ['LineString', 'Polygon']);
  assert.equal(overlay.metadata.variable, 'precipitation');
});
