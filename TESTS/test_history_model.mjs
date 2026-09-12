// The monthly record is the tab where a reader draws their own conclusions, so the
// arithmetic under it has to refuse the conclusions the record cannot support. A gap
// is not a zero, a line must not be drawn across one, an annual total over eleven
// observed months is not an annual total, and a series whose gaps grow towards the
// present has to say so before anyone reads a trend from it.
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  dateAt, extentOf, gapDrift, pathOf, segments, seriesNames, toCsv, yearRows,
} from '../INTERFACE/historyModel.js';

// Twenty years of monthly values, so a fixture exercises the same shape the store
// publishes without needing the store.
function history({ years = [2003, 2022], make = (index) => index } = {}) {
  const months = (years[1] - years[0] + 1) * 12;
  return {
    basin_id: '4121289400', basin_level: 12, years, months,
    series: {
      pre_mm_s: {
        label: 'precipitation', unit: 'millimetres per month', asset: 'IDAHO_EPSCOR/TERRACLIMATE',
        values: Array.from({ length: months }, (_, index) => make(index)),
        observed_months: months, missing_months: 0,
      },
    },
  };
}

test('a position carries its own date without the file repeating 240 of them', () => {
  const record = history();
  assert.deepEqual(dateAt(record, 0), { year: 2003, month: 1, label: 'Jan 2003' });
  assert.deepEqual(dateAt(record, 11), { year: 2003, month: 12, label: 'Dec 2003' });
  assert.deepEqual(dateAt(record, 12), { year: 2004, month: 1, label: 'Jan 2004' });
  assert.deepEqual(dateAt(record, 239), { year: 2022, month: 12, label: 'Dec 2022' });
});

test('a year reports what it observed, and withholds a total it does not have', () => {
  const record = history({ make: index => (index === 5 ? null : 10) });
  const rows = yearRows(record, 'pre_mm_s');
  assert.equal(rows.length, 20);

  const first = rows[0];
  assert.equal(first.year, 2003);
  assert.equal(first.observed, 11);
  assert.equal(first.whole, false);
  assert.equal(first.total, null, 'eleven months do not make an annual total');
  assert.equal(first.mean, 10, 'the mean is over what was observed, not over twelve');

  const second = rows[1];
  assert.equal(second.observed, 12);
  assert.equal(second.total, 120);
  assert.equal(second.whole, true);
});

test('a year with nothing observed reports nothing rather than zero', () => {
  const record = history({ make: index => (index < 12 ? null : 4) });
  const [first] = yearRows(record, 'pre_mm_s');
  assert.equal(first.observed, 0);
  assert.equal(first.mean, null);
  assert.equal(first.min, null);
  assert.equal(first.max, null);
  assert.equal(first.total, null);
});

test('a gap breaks the line instead of being drawn through', () => {
  const values = [1, 2, null, 4, 5];
  const extent = extentOf(values);
  const drawn = segments(values, extent, 100, 50);
  assert.equal(drawn.length, 2, 'the line is cut where the record is');
  assert.deepEqual(drawn.map(part => part.length), [2, 2]);
  assert.deepEqual(drawn.flat().map(point => point.value), [1, 2, 4, 5]);
  assert.ok(!pathOf(drawn[0]).includes('L' + drawn[1][0].x.toFixed(2)), 'no segment spans the gap');

  // A lone observation between two gaps has no line to be part of.
  const island = segments([null, 7, null], extentOf([null, 7, null]), 100, 50);
  assert.equal(island.length, 1);
  assert.equal(island[0].length, 1);
});

test('the extent is built from observations, so a gap cannot drag the axis', () => {
  assert.deepEqual(extentOf([null, null]), null);
  const range = extentOf([10, 20, null]);
  assert.ok(range.low < 10 && range.high > 20);
  assert.ok(range.low > 0, 'a gap must not pull the floor to zero');

  const flat = extentOf([5, 5, 5]);
  assert.ok(flat.low < 5 && flat.high > 5, 'a constant series still needs a drawable range');
});

test('a record that loses months towards the present says so', () => {
  // The snow case: nulls concentrated in the later years.
  const losing = history({ make: index => (index > 150 && index % 3 === 0 ? null : 1) });
  const drift = gapDrift(losing, 'pre_mm_s');
  assert.ok(drift.growing, 'gaps concentrated late must be flagged');
  assert.ok(drift.late > drift.early);

  const even = history({ make: index => (index % 40 === 0 ? null : 1) });
  assert.equal(gapDrift(even, 'pre_mm_s')?.growing, false, 'evenly spread gaps are not a drift');
  assert.equal(gapDrift(history(), 'pre_mm_s'), null, 'a whole record has no drift to report');
});

test('the download carries the gaps as empty cells, never as zeroes', () => {
  const record = history({ make: index => (index === 0 ? null : index) });
  const csv = toCsv(record);
  const lines = csv.trim().split('\n');
  assert.equal(lines[0], 'year,month,pre_mm_s');
  assert.equal(lines[1], '2003,1,', 'a month with no observation is an empty cell');
  assert.equal(lines[2], '2003,2,1');
  assert.equal(lines.length, 241, 'a header and every month of the record');
});

test('the variables are listed from the record itself', () => {
  const record = history();
  record.series.tmp_dc_s = { label: 'temperature', unit: 'degrees Celsius', values: [] };
  assert.deepEqual(seriesNames(record), ['pre_mm_s', 'tmp_dc_s']);
  assert.deepEqual(seriesNames({}), []);
  assert.deepEqual(yearRows(record, 'no such series'), []);
});
