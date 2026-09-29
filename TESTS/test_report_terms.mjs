import test from 'node:test';
import assert from 'node:assert/strict';
import { baselineNote, trendUnit } from '../INTERFACE/reportTerms.js';
import { totalDefinition } from '../INTERFACE/catchmentStatisticsModel.js';

test('a precipitation volume is called a precipitation volume, not runoff', () => {
  const rain = totalDefinition('pre_mm_s', 'millimetres per month');
  assert.equal(rain.label, 'Precipitation volume');
  assert.match(rain.note, /not runoff/);
  assert.doesNotMatch(rain.note, /runoff volume is generated/);
  assert.equal(totalDefinition('run_mm_s', 'millimetres per month').label, 'Generated runoff volume');
  assert.equal(totalDefinition('tmx_dc_s', 'degrees Celsius').factor, null);
});

test('a trend over annual totals is a change in the annual total per decade', () => {
  assert.equal(trendUnit('millimetres per month', true), 'millimetres per year, per decade');
  assert.equal(trendUnit('degrees Celsius', false), 'degrees Celsius per decade');
});

test('the two baselines are named apart', () => {
  const note = baselineNote(2003, 2025);
  assert.match(note, /2003–2025/);
  assert.match(note, /1991–2020/);
});
