import test from 'node:test';
import assert from 'node:assert/strict';
import { forecastUnits } from '../INTERFACE/seasonalModel.js';

const forecast = { units: { 'l7:4619100': {}, 'zone:amu_darya:headwater': {}, 'zone:syr_darya:lowland': {} } };

test('a level-12 basin reads its level-7 basin by Pfafstetter prefix, then its zone', () => {
  const units = forecastUnits(forecast, { pfaf_id: 461910012345, system_id: 'amu_darya', in_headwater_formation: 1 });
  assert.deepEqual(units.map(unit => unit.key), ['l7:4619100', 'zone:amu_darya:headwater']);
});

test('a level-7 basin reads itself, and a lowland basin its lowland zone', () => {
  assert.deepEqual(forecastUnits(forecast, { pfaf_id: 4619100, system_id: 'amu_darya', in_headwater_formation: 0 })
    .map(unit => unit.key), ['l7:4619100']);
  assert.deepEqual(forecastUnits(forecast, { pfaf_id: 111, system_id: 'syr_darya', in_headwater_formation: false })
    .map(unit => unit.key), ['zone:syr_darya:lowland']);
  assert.deepEqual(forecastUnits(forecast, null), []);
});
