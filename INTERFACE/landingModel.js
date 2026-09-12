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

// The reader's opacity setting applied to the river-system wash. The default keeps
// the light wash above; below it the wash fades towards nothing, above it rises to
// a solid colour, so the same slider means the same thing in both colourings.
const SYSTEM_FILL_MAX = 0.62;
const OUTLINE = 0.45;

function systemFill(opacity) {
  const setting = opacity === undefined ? 0.66 : Math.min(1, Math.max(0, Number(opacity)));
  if (setting <= 0.66) return FILL.base * (setting / 0.66);
  return FILL.base + (SYSTEM_FILL_MAX - FILL.base) * ((setting - 0.66) / (1 - 0.66));
}

export function basinStyle(properties, state = {}, opacity) {
  const { color } = systemMeta(properties?.system_id);
  const selected = Boolean(state.selected);
  const hovered = Boolean(state.hovered) && !selected;
  const base = systemFill(opacity);
  return {
    color,
    weight: selected ? 1.8 : hovered ? 1.2 : 0.35,
    opacity: selected || hovered ? 0.95 : Math.min(OUTLINE, Math.max(0.15, base * 3.3)),
    fillColor: color,
    fillOpacity: selected ? Math.max(FILL.selected, base + 0.2) : hovered ? Math.max(FILL.hovered, base + 0.12) : base,
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

export const OVERLAY_OPACITY = { default: 0.66, min: 0.1, max: 1 };

/** Clamp a reader's opacity choice, falling back to the default for anything unreadable. */
export function overlayOpacity(value) {
  const number = Number(value);
  if (value === null || value === '' || !Number.isFinite(number)) return OVERLAY_OPACITY.default;
  return Math.min(OVERLAY_OPACITY.max, Math.max(OVERLAY_OPACITY.min, number));
}

// `opacity` is the reader's setting for an ordinary basin. Hover and selection lift
// from it rather than to a fixed value, so a faint map still shows what is picked.
// The outline is drawn in the fill colour and fades with it, or a faint fill would
// leave a mesh of bright borders over the base map.
export function overlayStyle(properties, state, value, breaks, palette = CHOROPLETH, opacity = OVERLAY_OPACITY.default) {
  const base = basinStyle(properties, state);
  const fill = choroplethColor(value, breaks, palette);
  const level = overlayOpacity(opacity);
  if (!fill) return { ...base, fillOpacity: state?.selected ? 0.3 : 0.06 };
  const lifted = state?.selected ? level + 0.26 : state?.hovered ? level + 0.19 : level;
  return {
    ...base,
    fillColor: fill,
    fillOpacity: Math.min(1, lifted),
    opacity: state?.selected || state?.hovered ? base.opacity : Math.min(base.opacity, level),
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

// --------------------------------------------------- dam clustering

// A hundred barriers on a basin map is not a hundred readable circles: the
// Chirchik and Fergana groups overlap into one blob at national zoom, and a
// reader cannot tell three dams from one. So dams are grouped into cells whose
// size is fixed in *pixels* and therefore shrinks in degrees as the map zooms,
// which is what makes a group split apart under zoom rather than merely growing.
//
// The cell is a plain grid rather than a distance-based clustering pass. With a
// hundred points a grid is exact, runs on every zoom change without a frame
// budget, and — unlike a greedy nearest-neighbour pass — gives the same answer
// whatever order the dams arrive in, so a group never reshuffles between renders.
const CLUSTER_CELL_PIXELS = 52;
const WORLD_PIXELS_AT_ZOOM_0 = 256;

/** Grid cell size in degrees of longitude for a zoom level. */
export function damClusterCellSize(zoom) {
  const scale = WORLD_PIXELS_AT_ZOOM_0 * 2 ** Number(zoom || 0);
  return (CLUSTER_CELL_PIXELS * 360) / scale;
}

/**
 * Group dams into cells for one zoom level.
 *
 * Returns one entry per occupied cell, each carrying its members and their
 * totals. A cell holding a single dam is returned with `count` 1 and is drawn as
 * that dam rather than as a group, so zooming in never leaves a "1" bubble
 * sitting where the dam itself should be.
 */
/**
 * The grid itself, over any features and any way of reading their position.
 *
 * Dams are points and carry their coordinate in the geometry; lakes are polygons
 * and carry a separate label point in their properties. Both want exactly the
 * same grouping behaviour, so the grid is written once and told how to find a
 * position rather than being duplicated per layer.
 */
export function clusterPoints(features, zoom, positionOf, cellPixels = CLUSTER_CELL_PIXELS) {
  const cell = damClusterCellSize(zoom) * (cellPixels / CLUSTER_CELL_PIXELS);
  const cells = new Map();
  for (const feature of features || []) {
    const position = positionOf(feature) || [];
    const longitude = Number(position[0]);
    const latitude = Number(position[1]);
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) continue;
    const key = `${Math.floor(longitude / cell)}:${Math.floor(latitude / cell)}`;
    const bucket = cells.get(key) || { key, members: [], longitude: 0, latitude: 0 };
    bucket.members.push(feature);
    bucket.longitude += longitude;
    bucket.latitude += latitude;
    cells.set(key, bucket);
  }
  return [...cells.values()].map(bucket => ({
    ...bucket,
    count: bucket.members.length,
    longitude: bucket.longitude / bucket.members.length,
    latitude: bucket.latitude / bucket.members.length,
  })).sort((left, right) => left.key.localeCompare(right.key));
}

/**
 * Group stations that would otherwise draw on top of each other.
 *
 * Three hundred points is nothing to render, which is why they were drawn
 * individually at first, but rendering was never the problem: at national zoom the
 * network is dense enough that marks overlap, and an overlapped mark cannot be
 * clicked because a neighbour intercepts the pointer. Grouping is what makes them
 * selectable, not what makes them cheap.
 *
 * A group reports the least certain placement it contains, so a group is never
 * drawn more confidently than its weakest member.
 */
const PLACEMENT_RANK = ['departs_from_network_relationship', 'not_checked',
                        'consistent_with_network', 'coordinate_supplied_by_source'];

export function clusterStations(features, zoom) {
  return clusterPoints(features, zoom, feature => feature.geometry?.coordinates)
    .map(bucket => {
      const members = bucket.members.map(member => member.properties || {});
      const weakest = members.reduce((worst, row) => (
        PLACEMENT_RANK.indexOf(row.placement_status) < PLACEMENT_RANK.indexOf(worst)
          ? row.placement_status : worst
      ), PLACEMENT_RANK[PLACEMENT_RANK.length - 1]);
      // The group opens the member with the longest record: the one a reader is
      // most likely to want, and the one its label names.
      const fullest = members.reduce((best, row) => (
        Number(row.observations || 0) > Number(best?.observations || 0) ? row : best
      ), members[0]);
      return {
        key: bucket.key, count: bucket.count,
        longitude: bucket.longitude, latitude: bucket.latitude,
        members, fullest, placement_status: weakest,
        observations: members.reduce((total, row) => total + Number(row.observations || 0), 0),
      };
    });
}

/** Where a dam sits: a point feature, so straight from the geometry. */
const damPosition = feature => feature.geometry?.coordinates;

export function clusterDams(features, zoom) {
  const cells = new Map();
  for (const bucket of clusterPoints(features, zoom, damPosition)) cells.set(bucket.key, bucket);

  return [...cells.values()].map(bucket => {
    const properties = bucket.members.map(member => member.properties || {});
    const capacities = properties
      .map(row => Number(row.capacity_mcm))
      .filter(value => Number.isFinite(value) && value > 0);
    const largest = properties.reduce((best, row) => (
      (Number(row.capacity_mcm) || 0) > (Number(best?.capacity_mcm) || 0) ? row : best
    ), properties[0]);
    return {
      key: bucket.key,
      count: bucket.count,
      // A group sits at the mean of its members, so it lands among the dams it
      // stands for rather than at a cell corner none of them occupies.
      longitude: bucket.longitude,
      latitude: bucket.latitude,
      members: bucket.members,
      storageMcm: capacities.reduce((total, value) => total + value, 0),
      withCapacity: capacities.length,
      inFormationZone: properties.filter(row => Number(row.in_headwater_formation) === 1).length,
      largest,
    };
  }).sort((left, right) => left.key.localeCompare(right.key));
}

// A group is drawn from the storage it stands for, on the same logarithmic scale
// as a single dam, then widened a little so it reads as a group and stays big
// enough to carry its count.
const CLUSTER_RADIUS = { min: 11, max: 22 };

export function damClusterStyle(cluster, state = {}) {
  const base = damRadius(cluster?.storageMcm) ?? CLUSTER_RADIUS.min;
  const radius = Math.min(Math.max(base + 4, CLUSTER_RADIUS.min), CLUSTER_RADIUS.max);
  const formation = cluster?.inFormationZone > (cluster?.count || 0) / 2;
  const color = formation ? '#c77dff' : '#ff4d6d';
  const hovered = Boolean(state.hovered);
  return {
    radius,
    color: hovered ? '#ffffff' : '#1b0d12',
    weight: hovered ? 2.2 : 1,
    opacity: 1,
    fillColor: color,
    fillOpacity: hovered ? 0.95 : 0.85,
  };
}

/** Bounds of a group's members, for zooming into it. */
export function damClusterBounds(cluster) {
  let minLat = Infinity, maxLat = -Infinity, minLon = Infinity, maxLon = -Infinity;
  for (const member of cluster?.members || []) {
    const [longitude, latitude] = member.geometry?.coordinates || [];
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) continue;
    if (latitude < minLat) minLat = latitude;
    if (latitude > maxLat) maxLat = latitude;
    if (longitude < minLon) minLon = longitude;
    if (longitude > maxLon) maxLon = longitude;
  }
  return Number.isFinite(minLat) ? [[minLat, minLon], [maxLat, maxLon]] : null;
}

/** One line describing what a group holds, for its tooltip. */
export function damClusterLabel(cluster) {
  if (!cluster?.count) return '';
  if (cluster.count === 1) return damLabel(cluster.members[0].properties);
  const storage = cluster.storageMcm > 0 ? `, ${formatNumber(cluster.storageMcm)} MCM` : '';
  return `${cluster.count} dams${storage}`;
}

// ------------------------------------------------------ lake symbols

// Lakes are drawn twice: the shoreline polygon, which is the real geometry, and
// a symbol marking where the water body *is* when the polygon is too small to
// see. The symbol is a locator, not a measurement, so it stays one small fixed
// size at every zoom — scaling it by area would make it compete with the dam
// circles, which do carry magnitude.
const LAKE_SYMBOL_SIZE = { width: 17, height: 13 };

// Lake symbols group on a tighter grid than dams. A dam bubble carries a number
// and needs room; a lake symbol only has to stop two shorelines colliding, so a
// smaller cell keeps more individual lakes legible before they merge.
const LAKE_CELL_PIXELS = 34;

export const lakeSymbolSize = () => ({ ...LAKE_SYMBOL_SIZE });

/** Where a lake's symbol goes: a label point carried in its properties. */
export const lakePosition = feature => [
  Number(feature?.properties?.symbol_longitude),
  Number(feature?.properties?.symbol_latitude),
];

/**
 * Which lakes are worth drawing at all at this zoom.
 *
 * The full set is 1,393 water bodies down to 0.1 km². Drawing every one at
 * national zoom is unreadable and slow, so the floor drops as the reader moves
 * in and the small ponds appear only when there is room for them.
 */
export function lakeAreaFloor(zoom) {
  const level = Number(zoom) || 0;
  if (level < 7) return 10;
  if (level < 9) return 1;
  if (level < 11) return 0.25;
  return 0;
}

/**
 * Lake symbols for one zoom, grouped where they would overlap.
 *
 * Returns single entries and groups in one list. A group carries the largest
 * member so the map can name the water body a reader is most likely looking for,
 * and the count so the symbol can say how many are hidden behind it.
 */
export function clusterLakes(features, zoom) {
  const floor = lakeAreaFloor(zoom);
  const eligible = (features || []).filter(feature => {
    const area = Number(feature?.properties?.area_km2);
    return Number.isFinite(area) && area >= floor;
  });
  return clusterPoints(eligible, zoom, lakePosition, LAKE_CELL_PIXELS).map(bucket => {
    const largest = bucket.members.reduce((best, member) => (
      Number(member.properties?.area_km2 || 0) > Number(best.properties?.area_km2 || 0) ? member : best
    ), bucket.members[0]);
    return {
      key: bucket.key,
      count: bucket.count,
      longitude: bucket.longitude,
      latitude: bucket.latitude,
      members: bucket.members,
      largest: largest.properties,
      areaKm2: bucket.members.reduce((total, member) => total + (Number(member.properties?.area_km2) || 0), 0),
    };
  });
}

/**
 * The label a lake symbol carries.
 *
 * A group is named for its largest member with the rest counted, because "Charvak
 * +3" tells a reader where they are and "4 lakes" does not.
 */
export function lakeClusterLabel(cluster) {
  if (!cluster?.count) return '';
  const name = (cluster.largest?.display_name || cluster.largest?.name || '').trim() || 'Unnamed water body';
  return cluster.count === 1 ? name : `${name} +${cluster.count - 1}`;
}

/** Is this position inside a [[south, west], [north, east]] box? */
export function withinBounds(position, bounds) {
  if (!bounds) return true;
  const [longitude, latitude] = position || [];
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return false;
  const [[south, west], [north, east]] = bounds;
  return latitude >= south && latitude <= north && longitude >= west && longitude <= east;
}

/**
 * Does this water body have a real name, or only a catalogue identifier?
 *
 * 1,361 of the 1,393 bodies are unnamed in the sources and carry a placeholder
 * built from their id. Painting "Unnamed lake · 14344" across a map is noise
 * pretending to be information, so only the 32 genuinely named bodies — from
 * HydroLAKES or a linked Global Dam Watch reservoir — are ever labelled.
 */
export function lakeIsNamed(properties) {
  const source = (properties?.display_name_source || '').trim();
  return Boolean(source) && source !== 'catalogue identifier';
}

/**
 * Which lake symbols get a name painted on the map.
 *
 * Named bodies only, largest first, capped so a dense view stays readable, and
 * ranked against what is currently on screen — so zooming into a valley names
 * the reservoirs in it rather than only the ones that are large nationally.
 * Everything else still gives its name and area on hover.
 */
export function labelledLakes(clusters, zoom, limit = 24) {
  const named = (clusters || []).filter(cluster => lakeIsNamed(cluster?.largest));
  const ranked = [...named].sort((left, right) =>
    (Number(right.largest?.area_km2) || 0) - (Number(left.largest?.area_km2) || 0));
  return new Set(ranked.slice(0, limit).map(cluster => cluster.key));
}
