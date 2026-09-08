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
  { from: 500, weight: 3.4 },
  { from: 100, weight: 2.5 },
  { from: 20, weight: 1.7 },
  { from: 5, weight: 1.15 },
  { from: 0, weight: 0.75 },
];

/**
 * Rivers are the subject of this map, so they are drawn bright and sized by the
 * water they carry. A reach whose long-term average is not perennial is drawn
 * dashed and dimmed: it is a mapped channel, not a flowing river.
 */
export function riverStyle(properties) {
  const discharge = Number(properties?.discharge_cms) || 0;
  const perennial = properties?.channel_class === 'perennial';
  const weight = RIVER_WIDTHS.find(entry => discharge >= entry.from)?.weight ?? 0.75;
  return {
    color: perennial ? '#9fefff' : '#7d9aa8',
    weight,
    opacity: perennial ? 0.92 : 0.5,
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
