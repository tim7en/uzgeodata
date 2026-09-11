import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import {csvCell, downloadName, recordSummary, toCsv} from '../INTERFACE/stationModel.js';

const record = JSON.parse(readFileSync(
  new URL('../PUBLISHED/data/hydromet/stations/meteo-38475.json', import.meta.url), 'utf8'));

test('a blank cell and a zero stay different things', () => {
  assert.equal(csvCell(0), '0');
  assert.equal(csvCell(0.0), '0');
  assert.equal(csvCell(null), '');
  assert.equal(csvCell(undefined), '');
  assert.equal(csvCell(-12.5), '-12.5');
});

test('a value that would break the format is quoted, not mangled', () => {
  assert.equal(csvCell('air, mean'), '"air, mean"');
  assert.equal(csvCell('say "when"'), '"say ""when"""');
  assert.equal(csvCell('two\nlines'), '"two\nlines"');
  assert.equal(csvCell('plain'), 'plain');
});

test('the CSV carries the header the file declares and one line per row', () => {
  const text = toCsv(record);
  const lines = text.trimEnd().split('\n');
  assert.equal(lines[0], record.columns.join(','));
  assert.equal(lines.length, record.rows.length + 1, 'header plus every row');
  assert.ok(text.endsWith('\n'), 'the file ends with a newline');
});

test('a missing monthly value arrives as an empty cell, never as a zero', () => {
  const sparse = {columns: ['variable', 'year', 'month', 'value'],
                  rows: [['air_temperature_mean', 2003, 1, null],
                         ['air_temperature_mean', 2003, 2, 0]]};
  const lines = toCsv(sparse).trimEnd().split('\n');
  assert.equal(lines[1], 'air_temperature_mean,2003,1,');
  assert.equal(lines[2], 'air_temperature_mean,2003,2,0');
});

test('an empty or malformed record yields nothing rather than a broken file', () => {
  assert.equal(toCsv(null), '');
  assert.equal(toCsv({}), '');
  assert.equal(toCsv({columns: ['a']}), '');
});

test('the filename says which station and which archive', () => {
  const name = downloadName(record, 'csv');
  assert.match(name, /-monthly\.csv$/);
  assert.ok(name.includes(record.archive));
  assert.equal(downloadName({name: 'Ak-Baytal / 2', archive: 'nsidc'}, 'json'),
               'ak-baytal-2-nsidc-monthly.json');
  assert.equal(downloadName(null, 'csv'), 'station-monthly.csv');
});

test('the summary describes what a reader would be taking', () => {
  const summary = recordSummary(record);
  assert.equal(summary.rows, record.rows.length);
  assert.equal(summary.values + summary.missing, summary.rows);
  assert.ok(summary.firstYear <= summary.lastYear);
  assert.ok(summary.variables.length >= 1);
  assert.equal(recordSummary({rows: []}), null, 'nothing to describe');
});
