import assert from 'node:assert/strict';
import test from 'node:test';
import { DEFAULT_MAP_VIEW, MAP_VIEW_KEY, readMapView, saveMapView, collectionBounds } from '../INTERFACE/mapViewModel.js';

test('a moved map survives a reload with its center and zoom intact', () => {
  const data = new Map();
  const storage = { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value) };
  assert.deepEqual(readMapView(storage), DEFAULT_MAP_VIEW);
  saveMapView(storage, [41.3, 70.7], 11);
  assert.deepEqual(readMapView(storage), { center: [41.3, 70.7], zoom: 11 });
  saveMapView(storage, DEFAULT_MAP_VIEW.center, DEFAULT_MAP_VIEW.zoom);
  assert.deepEqual(readMapView(storage), DEFAULT_MAP_VIEW);
  assert.ok(data.has(MAP_VIEW_KEY));
});

test('missing, malformed, invalid, or inaccessible saved views cannot break the map', () => {
  for (const value of [null, '{bad', 'null', '{}', '{"center":[91,70],"zoom":6}',
    '{"center":[40,181],"zoom":6}', '{"center":[40,70],"zoom":20}',
    '{"center":[40,70],"zoom":-1}', '{"center":["40",70],"zoom":6}']) {
    assert.deepEqual(readMapView({ getItem: () => value }), DEFAULT_MAP_VIEW);
  }
  const blocked = { getItem() { throw Error('blocked'); }, setItem() { throw Error('blocked'); } };
  assert.deepEqual(readMapView(blocked), DEFAULT_MAP_VIEW);
  assert.doesNotThrow(() => saveMapView(blocked, [40,70], 6));
});

test('fit selection includes every polygon and multipolygon in latitude/longitude order', () => {
  const polygon = { geometry: { type: 'Polygon', coordinates: [[[60,38],[62,38],[62,40],[60,38]]] } };
  const multi = { geometry: { type: 'MultiPolygon', coordinates: [
    [[[65,41],[66,42],[67,41],[65,41]]], [[[68,37],[70,39],[69,37],[68,37]]],
  ] } };
  assert.deepEqual(collectionBounds([polygon, multi]), [[37,60],[42,70]]);
  assert.deepEqual(collectionBounds([polygon]), [[38,60],[40,62]]);
  assert.equal(collectionBounds([]), null);
  assert.equal(collectionBounds([{ geometry: null }]), null);
});
