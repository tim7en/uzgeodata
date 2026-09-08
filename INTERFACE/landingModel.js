// The landing map shows one thing: the reference basins of the two natural
// systems, coarse at first and finer as the reader zooms in. Everything a reader
// can ask afterwards hangs off the basin they pick, so the rules for choosing a
// level, colouring, summarising and reading an attribute live here where they can
// be tested rather than inside the map component.

export const SYSTEMS = {
  amu_darya: { label: 'Amu Darya', color: '#4cc9f0' },
  syr_darya: { label: 'Syr Darya', color: '#ffa552' },
};

const FALLBACK_SYSTEM = { label: 'Outside the two systems', color: '#7c8a92' };

// The basins are context, not the subject: the fill stays faint enough for the
// river network and the terrain to read straight through it, and lifts only far
// enough that the unit under the pointer is unmistakable.
const FILL = { base: 0.14, hovered: 0.3, selected: 0.44 };

export function systemMeta(systemId) {
  return SYSTEMS[systemId] || FALLBACK_SYSTEM;
}

export function basinStyle(properties, state = {}) {
  const { color } = systemMeta(properties?.system_id);
  const selected = Boolean(state.selected);
  const hovered = Boolean(state.hovered) && !selected;
  return {
    color,
    weight: selected ? 1.8 : hovered ? 1.2 : 0.35,
    opacity: selected || hovered ? 0.95 : 0.45,
    fillColor: color,
    fillOpacity: selected ? FILL.selected : hovered ? FILL.hovered : FILL.base,
  };
}

const POSITION_LABELS = {
  runoff_formation: 'Runoff formation',
  transit: 'Transit',
  endorheic_sink: 'Endorheic sink',
};

const CHANNEL_LABELS = {
  perennial: 'Perennial channel',
  intermittent: 'Intermittent channel',
  ephemeral_or_dry: 'Mapped channel, effectively dry',
  no_mapped_channel: 'No mapped channel',
};

export function positionLabel(value) {
  return POSITION_LABELS[value] || 'Position not classified';
}

export function channelLabel(value) {
  return CHANNEL_LABELS[value] || 'Channel not classified';
}

/** The few facts worth showing before anyone asks for the full attribute set. */
export function basinHeadline(properties) {
  if (!properties) return [];
  return [
    { label: 'This sub-basin', value: formatNumber(properties.area_km2), unit: 'km²' },
    { label: 'Upstream catchment', value: formatNumber(properties.upstream_km2), unit: 'km²' },
    { label: 'Position', value: positionLabel(properties.flow_position) },
    { label: 'Channel', value: channelLabel(properties.channel_class) },
  ];
}

export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const number = Number(value);
  // Small numbers earn a decimal or two; a trailing zero only adds noise, so the
  // precision is a ceiling rather than a fixed width.
  const decimals = Math.abs(number) < 10 && number % 1 !== 0 ? Math.max(digits, 2) : digits;
  return number.toLocaleString('en-US', { maximumFractionDigits: decimals });
}

/**
 * BasinATLAS stores a few fields scaled by ten to keep them integral — air
 * temperature is the common one. Showing the raw number against the catalogue's
 * "(x10)" unit string reads as a wrong measurement, so the scale is undone and
 * the plain unit shown instead.
 */
export function formatAttribute(value, units) {
  if (value === null || value === undefined) return { value: '—', unit: units || '' };
  const scaled = typeof units === 'string' && units.includes('(x10)');
  const number = scaled ? Number(value) / 10 : Number(value);
  return {
    value: formatNumber(number, scaled || Math.abs(number) < 100 ? 1 : 0),
    unit: scaled ? units.replace(' (x10)', '') : units || '',
  };
}

/** Columnar store: one array per attribute, aligned to the shared id list. */
export function readAttribute(store, hybasId, column) {
  if (!store) return null;
  const index = store.index instanceof Map
    ? store.index.get(Number(hybasId))
    : store.ids?.indexOf(Number(hybasId));
  if (index === undefined || index === null || index < 0) return null;
  const values = store.values?.[column];
  return values ? values[index] ?? null : null;
}

export function indexStore(store) {
  if (!store?.ids) return store;
  return { ...store, index: new Map(store.ids.map((id, position) => [Number(id), position])) };
}

/** Attributes of one group, in catalogue order, with values for one basin. */
export function groupAttributes(groups, store, hybasId, groupId) {
  const group = (groups?.groups || []).find(entry => entry.id === groupId);
  if (!group) return [];
  return group.categories.map(category => ({
    id: category.id,
    attributes: category.attributes.map(attribute => ({
      ...attribute,
      ...formatAttribute(readAttribute(store, hybasId, attribute.column), attribute.units),
    })),
  }));
}

export function groupSummary(groups, groupId) {
  const group = (groups?.groups || []).find(entry => entry.id === groupId);
  if (!group) return { label: '', attributeCount: 0, categories: 0 };
  return {
    label: group.label,
    attributeCount: group.attributeCount,
    categories: group.categories.length,
  };
}

export function systemTotals(features) {
  const totals = new Map();
  for (const feature of features || []) {
    const system = feature.properties?.system_id;
    const entry = totals.get(system) || { system, units: 0, areaKm2: 0, formationUnits: 0 };
    entry.units += 1;
    entry.areaKm2 += Number(feature.properties?.area_km2) || 0;
    entry.formationUnits += feature.properties?.in_headwater_formation ? 1 : 0;
    totals.set(system, entry);
  }
  return [...totals.values()].sort((left, right) => right.areaKm2 - left.areaKm2);
}

/**
 * Which basin level to draw at a given zoom.
 *
 * A whole-region view does not need 7,445 polygons: level 7 is 438 units and a
 * twelfth of the weight, so the first paint is cheap and detail arrives as the
 * reader zooms towards it. The ladder is published with the data rather than
 * hardcoded here, so re-cutting the levels does not need a code change.
 */
export function pickByZoom(zoom, entries) {
  const ordered = [...(entries || [])].sort((left, right) => left.minZoom - right.minZoom);
  if (!ordered.length) return null;
  let chosen = ordered[0];
  for (const entry of ordered) {
    if (zoom >= entry.minZoom) chosen = entry;
  }
  return chosen;
}

export function levelForZoom(zoom, ladder) {
  return pickByZoom(zoom, ladder?.levels);
}

/** River tiers follow the same zoom ladder as the basins they sit on. */
export function tierForZoom(zoom, ladder) {
  return pickByZoom(zoom, ladder?.tiers);
}

const RIVER_WIDTHS = [
  { from: 500, weight: 2.1 },
  { from: 100, weight: 1.5 },
  { from: 20, weight: 1.0 },
  { from: 5, weight: 0.7 },
  { from: 0, weight: 0.5 },
];

/**
 * Rivers are the subject of this map, so they are sized by the water they carry
 * and kept bright enough to follow — but thin, and slightly transparent, so a
 * dense headwater network reads as a network rather than a solid mat. A reach
 * whose long-term average is not perennial is drawn dashed and dimmer: it is a
 * mapped channel, not a flowing river.
 */
export function riverStyle(properties) {
  const discharge = Number(properties?.discharge_cms) || 0;
  const perennial = properties?.channel_class === 'perennial';
  const weight = RIVER_WIDTHS.find(entry => discharge >= entry.from)?.weight ?? 0.75;
  return {
    color: perennial ? '#9fefff' : '#7d9aa8',
    weight,
    opacity: perennial ? 0.72 : 0.38,
    dashArray: perennial ? null : '2 4',
    lineCap: 'round',
    lineJoin: 'round',
    interactive: false,
  };
}

export function carriesAttributes(properties, ladder) {
  const level = Number(properties?.basin_level);
  return level === Number(ladder?.attributeLevel);
}

// A sequential ramp that stays legible on a dark basemap: dark blue through
// teal and green to yellow, so the eye reads magnitude without a key.
export const CHOROPLETH = ['#2c3e6b', '#256f8f', '#20a08b', '#5fc463', '#bfe040', '#fde725'];

/** Attributes worth offering before a reader knows the catalogue exists. */
export const HEADLINE_ATTRIBUTES = [
  'dis_m3_pyr', 'run_mm_syr', 'pre_mm_syr', 'tmp_dc_syr', 'snw_pc_syr',
  'gla_pc_sse', 'ele_mt_sav', 'for_pc_sse', 'crp_pc_sse', 'ppd_pk_sav',
];

/**
 * Quantile breaks over the values that exist.
 *
 * Equal intervals would put almost every basin in one class: discharge, glacier
 * extent and population are all heavily skewed. Quantiles spread the classes over
 * the distribution actually present, and nulls are left out rather than counted
 * as zero — a basin with no measurement is not a basin measuring nothing.
 */
export function quantileBreaks(values, classes = CHOROPLETH.length) {
  const present = (values || []).filter(value => value !== null && value !== undefined && Number.isFinite(Number(value)))
    .map(Number)
    .sort((left, right) => left - right);
  if (!present.length) return [];
  const breaks = [];
  for (let index = 1; index < classes; index += 1) {
    const position = (present.length - 1) * (index / classes);
    const low = Math.floor(position);
    const high = Math.ceil(position);
    breaks.push(present[low] + (present[high] - present[low]) * (position - low));
  }
  // A skewed column can repeat a break; collapsing keeps classes distinct.
  return [...new Set(breaks)];
}

export function classOf(value, breaks) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return null;
  const number = Number(value);
  let index = 0;
  while (index < breaks.length && number >= breaks[index]) index += 1;
  return index;
}

export function choroplethColor(value, breaks, palette = CHOROPLETH) {
  const index = classOf(value, breaks);
  if (index === null) return null;
  return palette[Math.min(index, palette.length - 1)];
}

/** Legend rows, low class first, each with the range it covers. */
export function legendStops(breaks, palette = CHOROPLETH) {
  if (!breaks.length) return [];
  const edges = [null, ...breaks, null];
  return edges.slice(0, -1).map((from, index) => ({
    color: palette[Math.min(index, palette.length - 1)],
    from,
    to: edges[index + 1],
  }));
}

export function overlayStyle(properties, state, value, breaks, palette = CHOROPLETH) {
  const base = basinStyle(properties, state);
  const fill = choroplethColor(value, breaks, palette);
  if (!fill) return { ...base, fillOpacity: state?.selected ? 0.3 : 0.06 };
  return {
    ...base,
    fillColor: fill,
    fillOpacity: state?.selected ? 0.92 : state?.hovered ? 0.85 : 0.66,
    color: state?.selected || state?.hovered ? '#ffffff' : fill,
  };
}

// ----------------------------------------------------------------- dams

// Nominal storage in the two systems runs from 1.3 MCM to Toktogul's 19,500 —
// a 15,000-fold range spread almost evenly over five decades. That range is what
// decides the scale.
//
// The textbook encoding is area-proportional: circle area rises with the value,
// because area is what the eye reads as quantity. Here it cannot be used. A
// radius ratio of sqrt(15000) is 122, so a 2-pixel dot for the smallest dam puts
// Toktogul at 244 pixels — and clamping the top flattens exactly the reservoirs
// that matter. Sizing by area instead makes three quarters of the dams
// indistinguishable specks beside it.
//
// So the radius is logarithmic, and the legend says so and draws its reference
// circles at decade steps. A reader decodes magnitude from the key rather than
// by comparing areas, which is the honest trade for keeping every dam visible.
const DAM_RADIUS = { min: 3.4, max: 17, floorMcm: 1, ceilingMcm: 20000 };

// A dam whose capacity GDW never reported is not a dam holding nothing. It is
// drawn at its own fixed small size and hollow, so it is present on the map and
// cannot be misread as the smallest reservoir.
const DAM_UNKNOWN_RADIUS = 2.8;

// The choropleth underneath runs dark blue through teal and green to yellow, so
// a dam drawn in any of those hues disappears into whichever attribute happens to
// be on. These two sit outside that ramp entirely, and every circle carries a dark
// stroke so it separates from a bright basin as well as a dark one.
const DAM_COLORS = {
  reservoir: '#ff4d6d',
  formation: '#c77dff',
  unknown: '#e8eef2',
};
const DAM_EDGE = '#1b0d12';

/**
 * Circle radius in pixels for a reservoir's nominal storage, or null when the
 * source never reported one.
 */
export function damRadius(capacityMcm) {
  const capacity = Number(capacityMcm);
  if (capacityMcm === null || capacityMcm === undefined || capacityMcm === ''
    || !Number.isFinite(capacity) || capacity <= 0) return null;
  const { min, max, floorMcm, ceilingMcm } = DAM_RADIUS;
  const span = Math.log10(ceilingMcm / floorMcm);
  const position = Math.log10(Math.max(capacity, floorMcm) / floorMcm) / span;
  return min + (max - min) * Math.min(position, 1);
}

/**
 * Leaflet path options for one dam. Size carries storage; colour separates a dam
 * standing in a runoff-formation zone from one downstream of it, because a dam
 * that sits where the water is generated regulates a different thing from one
 * that sits where the water merely passes.
 */
export function damStyle(properties, state = {}) {
  const radius = damRadius(properties?.capacity_mcm);
  const known = radius !== null;
  const formation = Number(properties?.in_headwater_formation) === 1;
  const color = !known ? DAM_COLORS.unknown : formation ? DAM_COLORS.formation : DAM_COLORS.reservoir;
  const selected = Boolean(state.selected);
  const hovered = Boolean(state.hovered) && !selected;
  return {
    radius: known ? radius : DAM_UNKNOWN_RADIUS,
    color: selected || hovered ? '#ffffff' : known ? DAM_EDGE : color,
    weight: selected ? 2.4 : hovered ? 1.8 : 1,
    opacity: selected || hovered ? 1 : 0.85,
    fillColor: color,
    fillOpacity: !known ? 0 : selected ? 1 : hovered ? 0.95 : 0.82,
  };
}

/** Reference circles for the size key, smallest first. */
export function damLegendStops(steps = [10, 100, 1000, 10000]) {
  return steps.map(capacity => ({ capacity, radius: damRadius(capacity) }));
}

export function damLabel(properties) {
  const name = (properties?.dam_name || '').trim() || (properties?.reservoir_name || '').trim();
  if (name) return name;
  // GDW leaves three quarters of these unnamed. The river it dams is the next
  // most useful handle, and the identifier is the last resort.
  const river = (properties?.river || '').trim();
  return river ? `Unnamed dam on the ${river}` : `Dam ${properties?.dam_id ?? '—'}`;
}

const DAM_USE_LABEL = {
  Irrigation: 'Irrigation',
  Hydroelectricity: 'Hydroelectricity',
  'Water supply': 'Water supply',
  'Flood control': 'Flood control',
};

export function damUseLabel(properties) {
  const main = (properties?.main_use || '').trim();
  if (main) return DAM_USE_LABEL[main] || main;
  const listed = (properties?.uses || '').split(';').map(entry => entry.trim()).filter(Boolean);
  return listed.length ? listed.join(', ') : 'Purpose not reported';
}

/**
 * The facts worth showing beside a dam, in the order a reader asks for them.
 * A row whose source value is missing is kept and shown as "not reported" rather
 * than dropped, so the gap in GDW's coverage stays visible instead of looking
 * like a fact nobody wanted to display.
 */
export function damHeadline(properties) {
  const capacity = damRadius(properties?.capacity_mcm) === null
    ? null : Number(properties.capacity_mcm);
  const height = Number(properties?.dam_height_m);
  const power = Number(properties?.power_capacity_mw);
  const year = Number(properties?.year_completed);
  return [
    {
      label: 'Nominal storage',
      value: capacity === null ? 'Not reported' : formatNumber(capacity),
      unit: capacity === null ? '' : 'MCM',
    },
    {
      label: 'Dam height',
      value: Number.isFinite(height) && height > 0 ? formatNumber(height) : 'Not reported',
      unit: Number.isFinite(height) && height > 0 ? 'm' : '',
    },
    {
      label: 'Completed',
      value: Number.isFinite(year) && year > 0 ? String(year) : 'Not reported',
      unit: '',
    },
    {
      label: 'Installed power',
      value: Number.isFinite(power) && power > 0 ? formatNumber(power) : 'Not reported',
      unit: Number.isFinite(power) && power > 0 ? 'MW' : '',
    },
    { label: 'Primary use', value: damUseLabel(properties), unit: '' },
    { label: 'River', value: (properties?.river || '').trim() || 'Not reported', unit: '' },
    { label: 'Country', value: (properties?.country || '').trim() || 'Not reported', unit: '' },
  ];
}

/** Totals for the dams currently drawn, for the layer's own summary line. */
export function damTotals(features) {
  const rows = (features || []).map(feature => feature.properties || feature);
  const capacities = rows
    .map(row => Number(row.capacity_mcm))
    .filter(value => Number.isFinite(value) && value > 0);
  return {
    dams: rows.length,
    withCapacity: capacities.length,
    storageMcm: capacities.reduce((total, value) => total + value, 0),
    inFormationZone: rows.filter(row => Number(row.in_headwater_formation) === 1).length,
  };
}
