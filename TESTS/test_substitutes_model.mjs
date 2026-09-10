import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import {
  basinIsPublished, isUpstream, payloadMatchesBasin, storedUnitsValue, substituteRows,
} from '../INTERFACE/substitutesModel.js';

const read = name => JSON.parse(readFileSync(
  new URL(`../PUBLISHED/data/atlas/${name}`, import.meta.url), 'utf8'));

const index = read('substitutes-index.json');
const definitions = read(`substitutes/${index.run_id}/definitions.json`);
const basin = read(`substitutes/${index.run_id}/${index.basin_ids[0]}.json`);
const selected = {hybas_id: index.basin_ids[0], basin_level: index.basin_level};

test('every published attribute joins to its family, its value slot and a reason when empty', () => {
  const rows = substituteRows(definitions, basin);
  assert.equal(rows.length, definitions.attributes.length);
  for (const row of rows) {
    assert.ok(row.familyData, `${row.column} lost its family`);
    assert.equal(row.familyData.family, row.family);
    assert.ok(Object.hasOwn(basin.values, row.column), `${row.column} has no value slot`);
    assert.ok(row.value != null || row.pending_reason, `${row.column} is empty without a reason`);
  }
});

test('the supports partition the attributes and never overlap', () => {
  const upstream = substituteRows(definitions, basin, '', 'basin_accumulation');
  const local = substituteRows(definitions, basin, '', 'basin_specific');
  assert.equal(upstream.length + local.length, definitions.attributes.length);
  assert.ok(upstream.length && local.length);
  assert.ok(upstream.every(row => isUpstream(row.support)));
  assert.ok(local.every(row => !isUpstream(row.support)));
  const overlap = new Set(upstream.map(row => row.column));
  assert.ok(local.every(row => !overlap.has(row.column)));
});

test('the filter reads the column, the label, the category and the source name', () => {
  const one = substituteRows(definitions, basin, definitions.attributes[0].column);
  assert.equal(one.length, 1);
  assert.equal(one[0].column, definitions.attributes[0].column);

  // One free-text term over four fields: the category is matched in full, and a
  // term such as "Climate" also reaches TerraClimate and WorldClim by source name.
  const category = definitions.attributes[0].category;
  const byCategory = new Set(substituteRows(definitions, basin, category.toUpperCase()).map(row => row.column));
  const inCategory = definitions.attributes.filter(a => a.category === category);
  assert.ok(inCategory.every(a => byCategory.has(a.column)));
  assert.ok(byCategory.size >= inCategory.length);
  for (const row of substituteRows(definitions, basin, category.toUpperCase())) {
    const searched = `${row.column} ${row.label} ${row.category} ${row.familyData.source.name}`.toLowerCase();
    assert.ok(searched.includes(category.toLowerCase()), `${row.column} matched nothing`);
  }

  const source = definitions.families[definitions.attributes[0].family].source.name;
  const families = new Set(Object.values(definitions.families)
    .filter(f => f.source.name === source).map(f => f.family));
  const bySource = substituteRows(definitions, basin, source);
  assert.ok(bySource.length);
  assert.ok(bySource.every(row => families.has(row.family)));

  assert.equal(substituteRows(definitions, basin, 'no such attribute').length, 0);
});

test('a valid zero is an available substitute and a missing one stays missing', () => {
  const rows = substituteRows(definitions, basin);
  const zeros = rows.filter(row => row.value === 0);
  assert.ok(zeros.length, 'the pilot run publishes valid zeroes');
  assert.ok(zeros.every(row => row.value != null), 'a zero must not read as missing');
  const missing = rows.filter(row => row.value == null);
  assert.equal(rows.length - missing.length,
    Object.values(basin.values).filter(v => v.value != null).length);
});

test('substitutes belong to the basin and the run they were computed for', () => {
  assert.ok(basinIsPublished(index, selected));
  assert.ok(!basinIsPublished(index, {hybas_id: '4120050220', basin_level: index.basin_level}),
    'a basin outside the pilot has no substitutes');
  assert.ok(!basinIsPublished(index, {hybas_id: selected.hybas_id, basin_level: 6}),
    'a coarser parent unit is not the basin the value was computed for');

  assert.ok(payloadMatchesBasin(index, definitions, basin, selected));
  assert.ok(payloadMatchesBasin(index, definitions, basin, {...selected, hybas_id: Number(selected.hybas_id)}));
  assert.ok(!payloadMatchesBasin(index, definitions, {...basin, run_id: 'other-run'}, selected));
  assert.ok(!payloadMatchesBasin(index, {...definitions, run_id: 'other-run'}, basin, selected));
  assert.ok(!payloadMatchesBasin(index, definitions, {...basin, hybas_id: '4120050220'}, selected));
  assert.ok(!payloadMatchesBasin(index, definitions, {...basin, basin_level: 6}, selected));
});

test('stored-unit conversion keeps a zero and refuses units that do not convert', () => {
  const convertible = Object.values(definitions.families).find(f => f.units.convertible);
  const other = Object.values(definitions.families).find(f => !f.units.convertible);
  assert.ok(convertible && other, 'the run has both convertible and non-convertible families');
  assert.equal(storedUnitsValue(convertible, 0), 0);
  assert.equal(storedUnitsValue(convertible, 2), 2 * convertible.units.factor);
  assert.equal(storedUnitsValue(convertible, null), null);
  assert.equal(storedUnitsValue(other, 2), null);
});
