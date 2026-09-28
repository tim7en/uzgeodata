import test from 'node:test';
import assert from 'node:assert/strict';
import { mapFrame, project } from '../INTERFACE/reportFigures.js';

const polygon = points => ({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [points] } });
test('export map fits the complete upstream extent and a point outside the basin', () => {
  const local = polygon([[69, 40], [70, 40], [70, 41], [69, 40]]);
  const upstream = polygon([[70, 40], [74, 40], [74, 44], [70, 40]]);
  const input = { type: 'Feature', geometry: { type: 'Point', coordinates: [68, 39] } };
  const frame = mapFrame({ local_geometry: { features: [local] }, upstream_geometry: { features: [upstream] }, input });
  for (const point of [[69, 40], [74, 44], input.geometry.coordinates]) {
    const [x, y] = project(point);
    assert.ok(x * frame.scale - frame.left >= 79 && x * frame.scale - frame.left <= 1321);
    assert.ok(y * frame.scale - frame.top >= 79 && y * frame.scale - frame.top <= 801);
  }
  assert.ok(project([70, 44])[1] < project([70, 40])[1], 'north stays above south');
});

test('missing geometry is explicit and a point-only report has a finite map scale', () => {
  const empty = { local_geometry: { features: [] }, upstream_geometry: { features: [] }, input: { geometry: null } };
  assert.equal(mapFrame(empty), null);
  const frame = mapFrame({ ...empty, input: { geometry: { type: 'Point', coordinates: [70, 40] } } });
  assert.equal(frame.zoom, 13);
  assert.ok(Number.isFinite(frame.left) && Number.isFinite(frame.top));
});
