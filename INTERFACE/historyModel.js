// The history tab shows what a climatology was averaged from. Everything here is
// about not letting the reader draw a conclusion the record cannot support: a gap is
// never a zero, an annual total is only a total when every month is present, and a
// series whose gaps grow over time says so before anyone reads a trend off it.

export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Month index to the calendar year and month it stands for. The array starts at
// January of the first year and runs without interruption, which is what lets a
// position carry a date without every file repeating 240 of them.
export function dateAt(history, position) {
  const year = history.years[0] + Math.floor(position / 12);
  return { year, month: (position % 12) + 1, label: `${MONTHS[position % 12]} ${year}` };
}

export function seriesNames(history) {
  return Object.keys(history?.series || {}).sort();
}

// One year of a series, with its own completeness. A mean over eight observed
// months is a real number about a different thing from a mean over twelve, so the
// count travels with it and the total is withheld unless the year is whole.
export function yearRows(history, name) {
  const series = history?.series?.[name];
  if (!series) return [];
  const rows = [];
  for (let index = 0; index * 12 < series.values.length; index += 1) {
    const months = series.values.slice(index * 12, index * 12 + 12);
    const observed = months.filter(value => value != null);
    const year = history.years[0] + index;
    rows.push({
      year,
      months,
      observed: observed.length,
      mean: observed.length ? observed.reduce((a, b) => a + b, 0) / observed.length : null,
      min: observed.length ? Math.min(...observed) : null,
      max: observed.length ? Math.max(...observed) : null,
      total: observed.length === 12 && series.unit === 'millimetres per month'
        ? observed.reduce((a, b) => a + b, 0) : null,
      whole: observed.length === 12,
    });
  }
  return rows;
}

// The extent a chart should draw over. Built from the observed values alone, so a
// gap cannot drag an axis to zero and make a winter look like a drought.
export function extentOf(values) {
  const observed = values.filter(value => value != null);
  if (!observed.length) return null;
  const low = Math.min(...observed);
  const high = Math.max(...observed);
  if (low === high) return { low: low - 1, high: high + 1 };
  const pad = (high - low) * 0.06;
  return { low: low - pad, high: high + pad };
}

// Points for a line, broken wherever the record is. Returned as separate segments
// rather than one path, because joining across a gap draws a measurement that was
// never made.
export function segments(values, extent, width, height) {
  if (!extent) return [];
  const step = values.length > 1 ? width / (values.length - 1) : width;
  const scale = value => height - ((value - extent.low) / (extent.high - extent.low)) * height;
  const out = [];
  let current = [];
  values.forEach((value, index) => {
    if (value == null) {
      if (current.length) out.push(current);
      current = [];
      return;
    }
    current.push({ x: index * step, y: scale(value), value, index });
  });
  if (current.length) out.push(current);
  return out;
}

export function pathOf(segment) {
  return segment.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ');
}

// Whether the gaps are spread through the record or concentrated at one end. A
// series that loses months as it goes cannot be read for trend without explaining
// why, and this is what puts that warning on the page instead of in a ledger.
export function gapDrift(history, name) {
  const rows = yearRows(history, name);
  if (rows.length < 4) return null;
  const half = Math.floor(rows.length / 2);
  const missing = rows.map(row => 12 - row.observed);
  const early = missing.slice(0, half).reduce((a, b) => a + b, 0);
  const late = missing.slice(rows.length - half).reduce((a, b) => a + b, 0);
  if (!early && !late) return null;
  return { early, late, growing: late > early * 2 && late > 4 };
}

// The basin's record as a spreadsheet, so a reader can take it away and work on it
// rather than reading conclusions off a page someone else drew.
export function toCsv(history, names = seriesNames(history)) {
  const header = ['year', 'month', ...names];
  const lines = [header.join(',')];
  const months = history.series[names[0]]?.values.length || 0;
  for (let position = 0; position < months; position += 1) {
    const { year, month } = dateAt(history, position);
    const cells = names.map(name => {
      const value = history.series[name]?.values[position];
      return value == null ? '' : value;
    });
    lines.push([year, month, ...cells].join(','));
  }
  return `${lines.join('\n')}\n`;
}
