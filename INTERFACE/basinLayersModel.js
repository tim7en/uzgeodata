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
  const [year, month, suffix] = period.split('-');
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const label = `${year} \u00b7 ${MONTHS[Number(month) - 1]}`;
  if (grain === 'pentad' && suffix) return `${label} \u00b7 P${suffix.slice(1)}`;
  if (grain === 'day' && suffix) return `${label} \u00b7 ${Number(suffix)}`;
  return label;
}

// How a layer names the ground it covers. The selector used to concatenate the
// title, the counts and the raw scope slug into one line, which read as a single
// sentence and hid the one fact that separates two layers of the same variable:
// which frame the numbers were reduced over.
const SCOPE_LABELS = {
  full_basin: 'Amu + Syr \u00b7 full natural basins',
  headwater_formation: 'Upper Amu + Upper Syr \u00b7 runoff formation',
  national_intersection: 'Uzbekistan \u00b7 national intersection',
  aral_hydrographic_domain: 'Aral hydrographic domain',
};

const FRAME_TITLES = {
  full_basin: 'Amu Darya + Syr Darya basin frame',
  headwater_formation: 'Upper Amu + Upper Syr formation zones',
  national_intersection: 'Uzbekistan national intersection',
  aral_hydrographic_domain: 'Aral hydrographic domain',
};

const PERIOD_NOUNS = {
  day: ['daily date', 'daily dates'],
  pentad: ['pentad', 'pentads'],
  month: ['monthly period', 'monthly periods'],
  year: ['year', 'years'],
};

function countLabel(count, [singular, plural]) {
  const value = Number(count) || 0;
  return `${value.toLocaleString('en-US')} ${value === 1 ? singular : plural}`;
}

export function scopeLabel(scope) {
  return SCOPE_LABELS[scope] || String(scope || 'scope not declared').replaceAll('_', ' ');
}

export function frameTitle(layer) {
  return FRAME_TITLES[layer?.spatialScope] || scopeLabel(layer?.spatialScope);
}

export function unitLabel(layer) {
  const unit = layer?.spatialUnit?.toLowerCase() || '';
  const nouns = unit.includes('system') ? ['formation system', 'formation systems']
    : unit.includes('subbasin') ? ['subbasin', 'subbasins']
      : unit.includes('basin') ? ['basin', 'basins'] : ['unit', 'units'];
  return countLabel(layer?.coverage?.basins, nouns);
}

export function periodLabel(layer) {
  return countLabel(layer?.coverage?.periods, PERIOD_NOUNS[layer?.periodGrain] || ['period', 'periods']);
}
