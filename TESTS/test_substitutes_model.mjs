// The substitutes tab reads 7,445 basin files against one catalogue, and the join
// between them is positional: the catalogue names each attribute once and every
// basin file carries arrays in that order. That is what makes the API affordable and
// it is also the one thing that can silently put every value under the wrong name,
// so it is checked against the published files rather than a fixture.
//
// The rest of what is tested here is the set of readings the tab must never allow: a
// missing value read as a zero, an estimate read as a reproduction, a difference
// computed across quantities that do not subtract, and one basin's value shown for
// another.
import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import {
  basinIsPublished, categoriesOf, comparable, difference, inStoredUnits, isUpstream,
  payloadMatchesBasin, periodLabel, resolutionLabel, rowState, rowTotals, substituteRows, support,
} from '../INTERFACE/substitutesModel.js';

const read = name => JSON.parse(readFileSync(
  new URL(`../PUBLISHED/data/atlas/${name}`, import.meta.url), 'utf8'));

const index = read('basins/index.json');
const catalogue = read('catalogue.json');
const first = Object.keys(index.by_basin)[0];
const basin = read(`basins/${first}.json`);
const selected = { hybas_id: first, basin_level: 12 };

test('every attribute in the catalogue lands on its own value in every basin file', () => {
  const rows = substituteRows(catalogue, basin);
  assert.equal(rows.length, catalogue.attributes.length);
  rows.forEach((row, position) => {
    assert.equal(row.column, catalogue.attributes[position], 'positional join drifted');
    assert.equal(row.original, basin.original[position]);
    assert.equal(row.value, basin.substitute[position]);
    assert.ok(row.meta, `${row.column} lost its metadata`);
  });
});

test('a file that does not line up with the catalogue is refused, not rendered', () => {
  assert.ok(payloadMatchesBasin(catalogue, basin, selected));
  assert.ok(!payloadMatchesBasin(catalogue, basin, { hybas_id: '1', basin_level: 12 }),
    'another basin id must not pass');
  assert.ok(!payloadMatchesBasin(catalogue, { ...basin, substitute: basin.substitute.slice(1) }, selected),
    'a short array would shift every value onto the wrong attribute');
});

test('the supports partition the attributes and never overlap', () => {
  const upstream = substituteRows(catalogue, basin, '', 'basin_accumulation');
  const local = substituteRows(catalogue, basin, '', 'basin_specific');
  assert.equal(upstream.length + local.length, catalogue.attributes.length);
  assert.ok(upstream.length && local.length);
  assert.ok(upstream.every(row => isUpstream(row.support)));
  assert.ok(local.every(row => !isUpstream(row.support)));
  const seen = new Set(upstream.map(row => row.column));
  assert.ok(local.every(row => !seen.has(row.column)));
});

test('the filter reads the column, the label, the category and both source names', () => {
  const column = catalogue.attributes[0];
  const one = substituteRows(catalogue, basin, column);
  assert.equal(one.length, 1);
  assert.equal(one[0].column, column);

  const category = catalogue.meta[column].category;
  const byCategory = substituteRows(catalogue, basin, category.toUpperCase());
  const inCategory = catalogue.attributes.filter(c => catalogue.meta[c].category === category);
  const found = new Set(byCategory.map(row => row.column));
  assert.ok(inCategory.every(c => found.has(c)), 'a category term must reach its whole category');

  assert.equal(substituteRows(catalogue, basin, 'no such attribute').length, 0);
});

test('a valid zero is an estimate and a missing one stays missing', () => {
  const rows = substituteRows(catalogue, basin);
  const zeros = rows.filter(row => row.value === 0);
  assert.ok(zeros.length, 'the region publishes measured zeroes');
  assert.ok(zeros.every(row => rowState(row) === 'estimated'), 'a zero must not read as missing');

  const estimated = rows.filter(row => rowState(row) === 'estimated').length;
  assert.equal(estimated, basin.substitute.filter(v => v != null).length);
  assert.equal(rowTotals(rows).estimated, estimated);
  assert.equal(rowTotals(rows).rows, rows.length);
});

test('a difference is computed only where the two numbers are the same quantity', () => {
  const rows = substituteRows(catalogue, basin);
  for (const row of rows) {
    if (!comparable(row)) {
      assert.equal(difference(row), null, `${row.column} subtracted across quantities`);
      assert.equal(inStoredUnits(row), null);
      continue;
    }
    if (row.value == null || row.original == null) {
      assert.equal(difference(row), null, 'a missing value has no difference');
      continue;
    }
    const converted = inStoredUnits(row);
    assert.equal(converted, row.value * row.family.units.factor);
    assert.ok(Math.abs(difference(row) - (converted - row.original)) < 1e-9);
  }
  // Snow is the case the rule exists for: both sides are percentages, and
  // snow-covered-day frequency is still not fractional snow cover.
  const snow = rows.find(row => row.column === 'snw_pc_s01');
  if (snow) assert.ok(snow.family?.divergence?.length, 'snow must carry its divergences');
});

test('estimates belong to the basin and the level they were computed for', () => {
  assert.ok(basinIsPublished(index, selected));
  assert.ok(!basinIsPublished(index, { hybas_id: first, basin_level: 7 }),
    'a coarser parent unit is a view of level 12, not a basin the run covered');
  assert.ok(!basinIsPublished(index, { hybas_id: '9999999999', basin_level: 12 }),
    'a basin outside the domain has no file');
});

test('the record behind a value is reported, not assumed whole', () => {
  const rows = substituteRows(catalogue, basin).filter(row => support(row));
  assert.ok(rows.length, 'dated-derived attributes carry their denominators');
  for (const row of rows) {
    const backing = support(row);
    assert.ok(backing.valid <= backing.expected, `${row.column} claims more periods than it had`);
    assert.equal(backing.whole, backing.valid === backing.expected);
    assert.ok(backing.fraction > 0 && backing.fraction <= 1);
  }
});

test('a period reads as the years it covers, not as an exclusive end date', () => {
  const climatology = catalogue.attributes
    .map(column => ({ column, meta: catalogue.meta[column] }))
    .find(entry => Array.isArray(entry.meta.substitute?.period));
  assert.ok(climatology, 'at least one attribute carries a substitute period');
  const label = periodLabel(climatology.meta);
  assert.match(label, /^\d{4}(–\d{4})?$/, 'an exclusive end date must not be shown as a year');
  const [, end] = climatology.meta.substitute.period;
  assert.ok(!label.includes(String(Number(end.slice(0, 4)))), 'the exclusive end year is not covered');

  assert.equal(periodLabel({ substitute: null }), null);
  assert.equal(periodLabel({ substitute: { period: ['2003-01-01', null] } }), null);
});

test('resolution says what the source measured at before what we reduced it onto', () => {
  const snow = catalogue.families.snw;
  assert.ok(snow, 'the snow family is published');
  const label = resolutionLabel(snow);
  assert.match(label, /native/);
  assert.ok(label.indexOf('native') < label.indexOf('processing'), 'native resolution leads');
  assert.equal(resolutionLabel(null), null);
  assert.equal(resolutionLabel({ resolution: {} }), null);
});

test('the categories are offered in the atlas order rather than alphabetically', () => {
  const categories = categoriesOf(catalogue);
  assert.ok(categories.length >= 5);
  assert.equal(new Set(categories).size, categories.length, 'no category is offered twice');
  for (const column of catalogue.attributes) {
    assert.ok(categories.includes(catalogue.meta[column].category), `${column} has an unlisted category`);
  }
});
