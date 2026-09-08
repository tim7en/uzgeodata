import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import {
  SYSTEMS, basinHeadline, basinStyle, channelLabel, formatAttribute, formatNumber,
  CHOROPLETH, HEADLINE_ATTRIBUTES, carriesAttributes, choroplethColor, groupAttributes, groupSummary, indexStore, levelForZoom, positionLabel,
  legendStops, overlayStyle, quantileBreaks, readAttribute, riverStyle, systemMeta, systemTotals,
  tierForZoom,
  damHeadline, damLabel, damLegendStops, damRadius, damStyle, damTotals, damUseLabel,
  clusterDams, damClusterBounds, damClusterCellSize, damClusterLabel, damClusterStyle,
} from '../INTERFACE/landingModel.js';

const read = name => JSON.parse(readFileSync(
  new URL(`../PUBLISHED/data/hydroclimate/${name}`, import.meta.url), 'utf8'));

test('the two river systems are coloured apart and anything else is neutral', () => {
  assert.notEqual(SYSTEMS.amu_darya.color, SYSTEMS.syr_darya.color);
  assert.equal(systemMeta('amu_darya').label, 'Amu Darya');
  assert.equal(systemMeta('unknown').label, 'Outside the two systems');
});

test('a basin lifts out of the background on hover and again on selection', () => {
  const properties = {system_id: 'amu_darya'};
  const base = basinStyle(properties, {});
  const hovered = basinStyle(properties, {hovered: true});
  const selected = basinStyle(properties, {selected: true, hovered: true});
  assert.ok(base.fillOpacity > 0);
  assert.ok(hovered.fillOpacity > base.fillOpacity);
  assert.ok(selected.fillOpacity > hovered.fillOpacity);
  assert.ok(selected.weight > hovered.weight);
  assert.equal(base.fillColor, SYSTEMS.amu_darya.color);
});

test('a headline reads local area, upstream area, position and channel', () => {
  const rows = basinHeadline({
    area_km2: 132.4, upstream_km2: 76772.7,
    flow_position: 'runoff_formation', channel_class: 'ephemeral_or_dry',
  });
  assert.deepEqual(rows.map(row => row.label),
    ['This sub-basin', 'Upstream catchment', 'Position', 'Channel']);
  assert.equal(rows[1].value, '76,773');
  assert.equal(rows[2].value, 'Runoff formation');
  assert.equal(rows[3].value, 'Mapped channel, effectively dry');
  assert.equal(positionLabel('transit'), 'Transit');
  assert.equal(channelLabel('perennial'), 'Perennial channel');
});

test('a value stored at ten times scale is shown at its real magnitude', () => {
  // BasinATLAS keeps air temperature as degrees x10 so the column stays integral.
  assert.deepEqual(formatAttribute(78, 'degrees Celsius (x10)'), {value: '7.8', unit: 'degrees Celsius'});
  assert.deepEqual(formatAttribute(null, 'millimeters'), {value: '—', unit: 'millimeters'});
  assert.equal(formatNumber(null), '—');
});

test('an attribute is read out of the columnar store by basin id', () => {
  const store = indexStore({ids: [10, 20, 30], columns: ['pre_mm_syr'], values: {pre_mm_syr: [100, 200, 300]}});
  assert.equal(readAttribute(store, 20, 'pre_mm_syr'), 200);
  assert.equal(readAttribute(store, 99, 'pre_mm_syr'), null);
  assert.equal(readAttribute(null, 20, 'pre_mm_syr'), null);
});

test('the panel groups the published attributes without mixing the two kinds', () => {
  const groups = read('reference-attribute-groups.json');
  const store = indexStore(read('reference-basin-attributes.json'));
  const hybasId = store.ids[0];

  const specific = groupAttributes(groups, store, hybasId, 'basin_specific');
  const accumulated = groupAttributes(groups, store, hybasId, 'basin_accumulation');
  const columnsOf = categories => categories.flatMap(category => category.attributes.map(a => a.column));
  const left = new Set(columnsOf(specific));
  const right = new Set(columnsOf(accumulated));
  assert.ok(left.size > 0 && right.size > 0);
  assert.equal([...left].filter(column => right.has(column)).length, 0);
  assert.equal(left.size + right.size, store.columns.length);

  assert.equal(groupSummary(groups, 'basin_specific').attributeCount, left.size);
  assert.equal(groupSummary(groups, 'basin_accumulation').attributeCount, right.size);
  for (const category of specific) {
    for (const attribute of category.attributes) assert.ok(attribute.label && 'value' in attribute);
  }
});

test('system totals come from the published reference layer', () => {
  const totals = systemTotals(read('reference-basins-level12.geojson').features);
  assert.deepEqual(totals.map(entry => entry.system).sort(), ['amu_darya', 'syr_darya']);
  for (const entry of totals) {
    assert.ok(entry.units > 0);
    assert.ok(entry.areaKm2 > 0);
    assert.ok(entry.formationUnits <= entry.units);
  }
});

test('the drawn basin level follows the zoom, coarse first', () => {
  const ladder = read('reference-basin-levels.json');
  assert.equal(ladder.attributeLevel, 12);
  assert.deepEqual(ladder.levels.map(entry => entry.level), [7, 10, 12]);

  // A whole-region view must not pull the finest layer.
  assert.equal(levelForZoom(4, ladder).level, 7);
  assert.equal(levelForZoom(6, ladder).level, 7);
  assert.equal(levelForZoom(7, ladder).level, 10);
  assert.equal(levelForZoom(8, ladder).level, 10);
  assert.equal(levelForZoom(9, ladder).level, 12);
  assert.equal(levelForZoom(14, ladder).level, 12);
  assert.equal(levelForZoom(6, null), null);

  // The point of the ladder: the first paint is far lighter than the last.
  const first = ladder.levels.find(entry => entry.level === 7);
  const last = ladder.levels.find(entry => entry.level === 12);
  assert.ok(first.units < last.units);
  assert.ok(first.sizeBytes * 4 < last.sizeBytes, 'the coarse level should be far smaller');
  for (const entry of ladder.levels) assert.match(entry.url, /^\/data\/hydroclimate\/reference-basins-level\d\d\.geojson$/);
});

test('atlas attributes are only claimed for the level that carries them', () => {
  const ladder = read('reference-basin-levels.json');
  assert.equal(carriesAttributes({basin_level: 12}, ladder), true);
  assert.equal(carriesAttributes({basin_level: 7}, ladder), false);
  assert.equal(carriesAttributes({}, ladder), false);
  const carriers = ladder.levels.filter(entry => entry.carriesAtlasAttributes);
  assert.equal(carriers.length, 1);
  assert.equal(carriers[0].level, ladder.attributeLevel);
});

test('basins are faint enough to read the rivers through them', () => {
  const properties = {system_id: 'syr_darya'};
  assert.ok(basinStyle(properties, {}).fillOpacity <= 0.15);
  assert.ok(basinStyle(properties, {hovered: true}).fillOpacity <= 0.35);
  assert.ok(basinStyle(properties, {selected: true}).fillOpacity < 0.5);
  // Still a strict ladder, or hover would not read.
  assert.ok(basinStyle(properties, {}).fillOpacity
    < basinStyle(properties, {hovered: true}).fillOpacity);
});

test('a river is sized by the water it carries and dashed when it is not perennial', () => {
  const big = riverStyle({discharge_cms: 900, channel_class: 'perennial'});
  const small = riverStyle({discharge_cms: 2, channel_class: 'perennial'});
  assert.ok(big.weight > small.weight);
  assert.equal(big.dashArray, null);
  // Bright enough to follow, thin and slightly transparent so a dense network
  // still reads as separate lines rather than a solid mat.
  assert.ok(big.opacity > 0.6 && big.opacity < 0.85, `unexpected opacity ${big.opacity}`);
  assert.ok(big.weight <= 2.2, `the widest river should stay hairline, got ${big.weight}`);
  assert.ok(small.weight < 1);

  const dry = riverStyle({discharge_cms: 30, channel_class: 'ephemeral_or_dry'});
  assert.ok(dry.dashArray, 'a channel that carries no water must not read as a river');
  assert.ok(dry.opacity < big.opacity);
  assert.notEqual(dry.color, big.color);
  // Rivers never intercept a click meant for the basin underneath.
  assert.equal(big.interactive, false);
});

test('river tiers follow the same zoom ladder as the basins', () => {
  const rivers = read('reference-river-levels.json');
  const basins = read('reference-basin-levels.json');
  assert.deepEqual(rivers.tiers.map(entry => entry.minZoom), basins.levels.map(entry => entry.minZoom));
  assert.equal(tierForZoom(3, rivers).id, 'main');
  assert.equal(tierForZoom(7, rivers).id, 'tributary');
  assert.equal(tierForZoom(11, rivers).id, 'headwater');

  const first = rivers.tiers[0];
  const last = rivers.tiers[rivers.tiers.length - 1];
  assert.ok(first.reaches < last.reaches);
  assert.ok(first.minDischargeCms > last.minDischargeCms);
  // The whole overlay must stay small beside the basins it sits on.
  assert.ok(first.sizeBytes < basins.levels[0].sizeBytes * 2);
});

test('a choropleth spreads classes over the values that exist', () => {
  // Equal intervals would put nearly every basin in one class: discharge,
  // glacier extent and population are all heavily skewed.
  const skewed = [0, 0, 1, 1, 2, 3, 5, 8, 40, 900, null, undefined];
  const breaks = quantileBreaks(skewed);
  assert.ok(breaks.length > 0 && breaks.length <= CHOROPLETH.length - 1);
  assert.deepEqual(breaks, [...breaks].sort((a, b) => a - b));

  assert.equal(choroplethColor(null, breaks), null, 'no measurement must not read as a low value');
  assert.equal(choroplethColor(900, breaks), CHOROPLETH[CHOROPLETH.length - 1]);
  assert.equal(choroplethColor(0, breaks), CHOROPLETH[0]);
  assert.equal(quantileBreaks([]).length, 0);
  assert.equal(quantileBreaks([null, null]).length, 0);
});

test('the legend covers every class from open low to open high', () => {
  const breaks = quantileBreaks([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
  const stops = legendStops(breaks);
  assert.equal(stops.length, breaks.length + 1);
  assert.equal(stops[0].from, null, 'the lowest class is open ended');
  assert.equal(stops[stops.length - 1].to, null, 'the highest class is open ended');
  for (let index = 1; index < stops.length; index += 1) {
    assert.equal(stops[index].from, stops[index - 1].to, 'classes must not leave a gap');
  }
  assert.equal(legendStops([]).length, 0);
});

test('an unmeasured basin stays unfilled under an overlay', () => {
  const breaks = quantileBreaks([1, 5, 9, 20]);
  const properties = {system_id: 'amu_darya'};
  const measured = overlayStyle(properties, {}, 9, breaks);
  const blank = overlayStyle(properties, {}, null, breaks);
  assert.ok(measured.fillOpacity > 0.5, 'a measured basin has to read as coloured');
  assert.ok(blank.fillOpacity < 0.1, 'a basin with no value must not look like a low value');
  assert.equal(overlayStyle(properties, {selected: true}, 9, breaks).color, '#ffffff');
});

test('every headline attribute offered on the map exists in the published groups', () => {
  const groups = read('reference-attribute-groups.json');
  const columns = new Set(groups.groups.flatMap(group =>
    group.categories.flatMap(category => category.attributes.map(a => a.column))));
  for (const column of HEADLINE_ATTRIBUTES) {
    assert.ok(columns.has(column), `${column} is offered but not published`);
  }
});

test('every level publishes the attribute store its overlay needs', () => {
  const ladder = read('reference-basin-levels.json');
  for (const entry of ladder.levels) {
    assert.match(entry.attributesUrl, /^\/data\/hydroclimate\/reference-basin-attributes/);
    assert.ok(entry.attributesBytes > 0);
  }
  // The coarse level must stay cheap: it loads before anyone has zoomed.
  const coarse = ladder.levels[0];
  const fine = ladder.levels[ladder.levels.length - 1];
  assert.ok(coarse.attributesBytes * 4 < fine.attributesBytes);
});

test('the whole related dataset resolves for a single watershed', () => {
  // What the modal renders: every attribute, its value, its kind, and the source
  // it came from — for one basin, in one pass.
  const groups = read('reference-attribute-groups.json');
  const store = indexStore(read('reference-basin-attributes.json'));
  const catalogue = read('reference-attribute-catalogue.json');
  const hybasId = store.ids[Math.floor(store.ids.length / 2)];

  const rows = ['basin_specific', 'basin_accumulation'].flatMap(groupId =>
    groupAttributes(groups, store, hybasId, groupId).flatMap(category =>
      category.attributes.map(attribute => ({ ...attribute, groupId, category: category.id }))));

  assert.equal(rows.length, store.columns.length, 'every published column must reach the table');
  for (const row of rows.slice(0, 40)) {
    assert.ok(row.label && row.spatialExtentLabel && row.category);
    assert.ok('value' in row);
    const code = catalogue.columnIndex[row.column]?.variable;
    const variable = catalogue.variables.find(entry => entry.code === code);
    assert.ok(variable?.source, `${row.column} has no source to show`);
    assert.ok(variable?.licence, `${row.column} has no licence to show`);
    assert.equal(catalogue.columnIndex[row.column].group, row.groupId);
  }
});

test('a basin resolves only in the store of its own level', () => {
  // HydroBASINS id spaces do not overlap between levels, so reading a level-7
  // basin out of the level-10 store returns nothing for all 281 columns. The
  // panel must pick the store by the selected basin's level, not by the drawn one.
  const seven = indexStore(read('reference-basin-attributes-level07.json'));
  const ten = indexStore(read('reference-basin-attributes-level10.json'));
  const twelve = indexStore(read('reference-basin-attributes.json'));
  assert.equal(seven.basinLevel, 7);
  assert.equal(ten.basinLevel, 10);
  assert.equal(twelve.basinLevel, 12);

  const sevenIds = new Set(seven.ids);
  assert.equal(ten.ids.filter(id => sevenIds.has(id)).length, 0);
  assert.equal(twelve.ids.filter(id => sevenIds.has(id)).length, 0);

  const probe = seven.ids[0];
  assert.notEqual(readAttribute(seven, probe, 'ele_mt_sav'), null);
  assert.equal(readAttribute(ten, probe, 'ele_mt_sav'), null, 'cross-level lookup must not silently succeed');
});

test('each level carries its own aggregate, not a copy of a finer unit', () => {
  const seven = indexStore(read('reference-basin-attributes-level07.json'));
  const twelve = indexStore(read('reference-basin-attributes.json'));
  const geo7 = read('reference-basins-level07.geojson').features;
  const geo12 = read('reference-basins-level12.geojson').features;

  const children = new Map();
  for (const feature of geo12) {
    const prefix = String(feature.properties.pfaf_id).slice(0, 7);
    children.set(prefix, [...(children.get(prefix) || []), feature.properties]);
  }
  const parent = geo7
    .map(feature => ({props: feature.properties, kids: children.get(String(feature.properties.pfaf_id)) || []}))
    .sort((left, right) => right.kids.length - left.kids.length)[0];
  assert.ok(parent.kids.length > 20, 'need a level-7 unit with many children to compare');

  const column = 'ele_mt_sav';
  const parentValue = readAttribute(seven, parent.props.hybas_id, column);
  const childValues = parent.kids
    .map(kid => readAttribute(twelve, kid.hybas_id, column))
    .filter(value => value !== null);
  assert.ok(childValues.length > 10);
  // A real aggregate sits inside the spread of its children rather than repeating one.
  assert.ok(parentValue >= Math.min(...childValues) && parentValue <= Math.max(...childValues),
    `level-7 ${column} ${parentValue} outside child range`);
  assert.notEqual(parentValue, childValues[0]);
});

test('a dam is sized by its storage, and the scale keeps every dam visible', () => {
  const smallest = damRadius(1.3);
  const median = damRadius(55);
  const toktogul = damRadius(19500);
  assert.ok(smallest < median && median < toktogul, 'radius has to rise with storage');
  // The point of the log scale: a 15,000-fold range still fits in a usable
  // spread of pixels, and the smallest dam stays big enough to click.
  assert.ok(smallest >= 3, `smallest dam ${smallest}px is too small to hit`);
  assert.ok(toktogul <= 18, `largest dam ${toktogul}px would swallow the map`);
  // Decade steps are evenly spaced, which is what makes the key readable.
  const decades = [10, 100, 1000, 10000].map(damRadius);
  const gaps = decades.slice(1).map((radius, index) => radius - decades[index]);
  for (const gap of gaps) assert.ok(Math.abs(gap - gaps[0]) < 0.01, 'decades must be evenly spaced');
});

test('a dam with no reported capacity is not drawn as a dam holding nothing', () => {
  for (const missing of [null, undefined, '', 0, -99]) {
    assert.equal(damRadius(missing), null, `${missing} should have no size`);
  }
  const unknown = damStyle({capacity_mcm: ''});
  const smallest = damStyle({capacity_mcm: 1.3});
  assert.equal(unknown.fillOpacity, 0, 'an unreported capacity is drawn hollow');
  assert.ok(smallest.fillOpacity > 0);
  assert.ok(unknown.radius < smallest.radius, 'and smaller than the smallest known dam');
});

test('a dam in a runoff-formation zone is coloured apart from one downstream', () => {
  const formation = damStyle({capacity_mcm: 500, in_headwater_formation: 1});
  const transit = damStyle({capacity_mcm: 500, in_headwater_formation: 0});
  assert.notEqual(formation.fillColor, transit.fillColor);
  assert.equal(formation.radius, transit.radius, 'colour carries role, size carries storage');
  const hovered = damStyle({capacity_mcm: 500}, {hovered: true});
  const selected = damStyle({capacity_mcm: 500}, {selected: true});
  assert.ok(selected.weight > hovered.weight);
});

test('an unnamed dam still gets a usable label', () => {
  assert.equal(damLabel({dam_name: 'Nurek'}), 'Nurek');
  assert.equal(damLabel({dam_name: '', reservoir_name: "Toktogul'skoye"}), "Toktogul'skoye");
  assert.equal(damLabel({river: 'Zeravshan'}), 'Unnamed dam on the Zeravshan');
  assert.equal(damLabel({dam_id: 4692}), 'Dam 4692');
});

test('a missing attribute is reported as missing rather than dropped', () => {
  const rows = damHeadline({capacity_mcm: '2000', dam_height_m: '168', year_completed: '1977',
    power_capacity_mw: '', main_use: 'Hydroelectricity', river: 'Chirchik', country: 'Uzbekistan'});
  const byLabel = Object.fromEntries(rows.map(row => [row.label, row]));
  assert.equal(byLabel['Nominal storage'].value, '2,000');
  assert.equal(byLabel['Nominal storage'].unit, 'MCM');
  assert.equal(byLabel['Dam height'].value, '168');
  assert.equal(byLabel['Completed'].value, '1977');
  // GDW reports no installed power anywhere in these basins; the row stays.
  assert.equal(byLabel['Installed power'].value, 'Not reported');
  assert.equal(byLabel['Installed power'].unit, '');
  assert.equal(damUseLabel({main_use: '', uses: 'irrigation;water supply'}), 'irrigation, water supply');
  assert.equal(damUseLabel({}), 'Purpose not reported');
});

test('the published dams carry what the map draws', () => {
  const dams = read('dams-transboundary.geojson').features;
  const totals = damTotals(dams);
  assert.ok(totals.dams > 50, 'the two systems should hold a hundred barriers');
  assert.ok(totals.withCapacity < totals.dams, 'GDW leaves some capacities unreported');
  assert.ok(totals.storageMcm > 60000, 'Toktogul, Rogun and Nurek alone exceed 40,000 MCM');

  // Every dam has to be drawable: a point, and either a size or the hollow marker.
  for (const dam of dams) {
    assert.equal(dam.geometry.type, 'Point');
    const [longitude, latitude] = dam.geometry.coordinates;
    assert.ok(longitude > 55 && longitude < 80, `${longitude} outside the two systems`);
    assert.ok(latitude > 33 && latitude < 48, `${latitude} outside the two systems`);
    const style = damStyle(dam.properties);
    assert.ok(style.radius > 0);
    assert.ok(damLabel(dam.properties).length > 0);
    assert.equal(damHeadline(dam.properties).length, 7);
  }

  const named = Object.fromEntries(dams.map(dam => [dam.properties.dam_name, dam.properties]));
  // The reservoirs that decide how much water reaches Uzbekistan.
  for (const name of ['Nurek', 'Toktogul', 'Charvak', 'Andizhan', 'Kayrakkum', 'Rogun']) {
    assert.ok(named[name], `${name} is missing from the dam layer`);
    assert.ok(damRadius(named[name].capacity_mcm) > 0, `${name} has no drawable storage`);
  }
  assert.ok(damRadius(named.Toktogul.capacity_mcm) > damRadius(named.Charvak.capacity_mcm),
    'Toktogul holds ten times Charvak and must draw larger');
});

test('the size key spans the decades the data actually covers', () => {
  const stops = damLegendStops();
  assert.equal(stops.length, 4);
  for (const stop of stops) assert.ok(stop.radius > 0);
  const dams = read('dams-transboundary.geojson').features;
  const capacities = dams.map(dam => Number(dam.properties.capacity_mcm)).filter(Boolean);
  assert.ok(Math.min(...capacities) < stops[0].capacity, 'key should start below the smallest dam');
  assert.ok(Math.max(...capacities) > stops.at(-1).capacity, 'and end below the largest');
});

test('dam groups split apart as the map zooms in', () => {
  const dams = read('dams-transboundary.geojson').features;
  const counts = [5, 6, 7, 8, 9, 10, 12].map(zoom => clusterDams(dams, zoom).length);
  for (let index = 1; index < counts.length; index += 1) {
    assert.ok(counts[index] >= counts[index - 1],
      `zooming in must not merge groups: ${counts}`);
  }
  assert.ok(counts.at(-1) > counts[0] * 3, 'a national view should group far more than a local one');
  // Every dam belongs to exactly one group at every zoom.
  for (const zoom of [5, 8, 12]) {
    const clusters = clusterDams(dams, zoom);
    assert.equal(clusters.reduce((total, c) => total + c.count, 0), dams.length);
    const seen = new Set(clusters.flatMap(c => c.members.map(m => m.properties.dam_id)));
    assert.equal(seen.size, dams.length, `zoom ${zoom} lost or duplicated a dam`);
  }
  // Cells shrink with zoom, which is what makes the split happen.
  assert.ok(damClusterCellSize(6) > damClusterCellSize(9));
});

test('grouping does not depend on the order the dams arrive in', () => {
  const dams = read('dams-transboundary.geojson').features;
  const shuffled = [...dams].reverse();
  const one = clusterDams(dams, 7).map(c => `${c.key}:${c.count}`);
  const two = clusterDams(shuffled, 7).map(c => `${c.key}:${c.count}`);
  assert.deepEqual(one, two);
});

test('a group carries the totals it stands for and sits among its members', () => {
  const dams = read('dams-transboundary.geojson').features;
  const clusters = clusterDams(dams, 6);
  const group = clusters.filter(c => c.count > 1).sort((a, b) => b.count - a.count)[0];
  assert.ok(group, 'expected at least one multi-dam group at national zoom');
  const expected = group.members
    .map(m => Number(m.properties.capacity_mcm)).filter(Number.isFinite)
    .reduce((total, value) => total + value, 0);
  assert.ok(Math.abs(group.storageMcm - expected) < 0.01);
  const bounds = damClusterBounds(group);
  assert.ok(group.latitude >= bounds[0][0] && group.latitude <= bounds[1][0]);
  assert.ok(group.longitude >= bounds[0][1] && group.longitude <= bounds[1][1]);
  assert.match(damClusterLabel(group), /\d+ dams/);
  // A lone dam is labelled as itself, never as a group of one.
  const single = clusters.find(c => c.count === 1);
  assert.doesNotMatch(damClusterLabel(single), /dams/);
});

test('a group is drawn larger than a single dam and stays inside its bounds', () => {
  const small = damClusterStyle({ storageMcm: 1, count: 2, inFormationZone: 0 });
  const large = damClusterStyle({ storageMcm: 40000, count: 9, inFormationZone: 0 });
  assert.ok(small.radius >= 11 && large.radius <= 22);
  assert.ok(large.radius > small.radius);
  assert.ok(small.radius > damRadius(1), 'a group must read larger than one dam');
  // Colour follows where the majority of the group stands.
  const formation = damClusterStyle({ storageMcm: 100, count: 3, inFormationZone: 3 });
  const transit = damClusterStyle({ storageMcm: 100, count: 3, inFormationZone: 0 });
  assert.notEqual(formation.fillColor, transit.fillColor);
});
