// Pure functions over the /data/basin-layers contract: {basins:{id:{period:{variable:{v,[z],[c]}}}}}.
// No React here so the colour and aggregation logic can be unit tested directly.

export function cellAt(series, basinId, period, variable) {
  return series?.basins?.[basinId]?.[period]?.[variable] || null;
}

export function valueAt(series, basinId, period, variable) {
  const cell = cellAt(series, basinId, period, variable);
  return cell ? cell.v : null;
}

export function timelineFor(series, basinId, periods, variable) {
  return periods.map(period => {
    const cell = cellAt(series, basinId, period, variable);
    return { period, v: cell ? cell.v : null, z: cell ? cell.z ?? null : null, c: cell ? cell.c ?? null : null };
  });
}

// Every basin's cell for one period and variable, for the map's colour scale and the histogram.
export function periodValues(series, period, variable) {
  const basins = series?.basins || {};
  const values = [];
  for (const basin of Object.keys(basins)) {
    const cell = basins[basin]?.[period]?.[variable];
    if (cell && Number.isFinite(cell.v)) values.push({ basin, v: cell.v, z: cell.z ?? null });
  }
  return values;
}

export function summaryStats(values) {
  if (!values.length) return { min: null, max: null, mean: null, median: null };
  const sorted = [...values].sort((a, b) => a - b);
  const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
  return {
    min: sorted[0], max: sorted.at(-1), mean,
    median: sorted[Math.floor(sorted.length / 2)],
  };
}

function hexToRgb(hex) {
  const value = hex.replace('#', '');
  return [0, 2, 4].map(index => parseInt(value.slice(index, index + 2), 16));
}

export function mix(a, b, amount) {
  const t = Math.min(1, Math.max(0, amount));
  const left = hexToRgb(a); const right = hexToRgb(b);
  const channel = index => Math.round(left[index] + (right[index] - left[index]) * t)
    .toString(16).padStart(2, '0');
  return `#${channel(0)}${channel(1)}${channel(2)}`;
}

// Sequential: how large is this value against everything observed this period, on one hue.
export function sequentialColor(value, min, max, color, base = '#172121') {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  const spread = Math.max(max - min, 1e-9);
  const amount = Math.min(Math.max((value - min) / spread, 0), 1);
  return mix(base, color, 0.12 + amount * 0.88);
}

// Diverging: which side of normal, and by how much, generic to any anomaly variable.
export function divergingColor(z, maxAbsZ, base = '#263134', low = '#39a7ff', high = '#ff695d') {
  if (z === null || z === undefined || !Number.isFinite(z)) return null;
  const amount = Math.min(Math.abs(z) / Math.max(maxAbsZ, 1e-9), 1);
  return mix(base, z < 0 ? low : high, 0.2 + amount * 0.8);
}

export function formatPeriod(grain, period) {
  if (grain === 'year') return period;
  const [year, month, pentad] = period.split('-');
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const label = `${year} \u00b7 ${MONTHS[Number(month) - 1]}`;
  if (grain === 'pentad' && pentad) return `${label} \u00b7 P${pentad.slice(1)}`;
  return label;
}
