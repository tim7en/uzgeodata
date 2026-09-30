// Upstream of a basin, taken apart: which sub-basins made the catchment's anomaly,
// whether its winter went into snow, and what river gauges stand inside it.
//
// A report that says upstream precipitation was 4% above normal answers little. The
// same 4% can be every headwater slightly wet, or one range very wet and the rest
// dry; a wet winter can build the snowpack that feeds next summer's river or fall as
// rain and leave it thin. These are the questions a water manager asks next.

import { polygonContains, polygonsOf } from './aoiModel.js';

const waterYearMonths = (index, waterYear) => {
  // October of the year before to September, as positions in the monthly frame.
  const first = (waterYear - 1 - index.years[0]) * 12 + 9;
  return Array.from({ length: 12 }, (_, offset) => first + offset);
};

function basinWaterYear(index, values, position, months, extensive) {
  let sum = 0;
  for (const month of months) {
    if (month < 0 || month >= index.months) return null;
    const encoded = values[position * index.months + month];
    if (encoded === index.null_sentinel) return null;
    sum += encoded / index.scale;
  }
  return extensive ? sum : sum / months.length;
}

/**
 * Each upstream basin's share of the catchment's water-year anomaly.
 *
 * The catchment anomaly is the area-weighted mean of its basins' anomalies, so each
 * basin contributes area share x its own anomaly, and the contributions add up to
 * the catchment figure exactly. The water year is the latest one every basin holds
 * completely in the gridded record; the normal is each basin's own mean over every
 * complete water year of that record. Basins are grouped into their level-7 basins
 * (by Pfafstetter prefix) so a reader sees ranges, not hundreds of units.
 */
export function upstreamAttribution(index, values, members, { extensive, pfafById = new Map(), minimumYears = 10 }) {
  if (members.length < 2) return null;
  const firstYear = index.years[0] + 1, lastYear = index.years[1];
  const complete = [];
  for (let year = firstYear; year <= lastYear; year += 1) {
    const months = waterYearMonths(index, year);
    const row = members.map(position => basinWaterYear(index, values, position, months, extensive));
    if (row.every(value => value !== null)) complete.push({ year, row });
  }
  if (complete.length < minimumYears + 1) return null;
  const latest = complete.at(-1);
  const baseline = complete;
  const area = members.map(position => index.areas_km2[position]);
  const total = area.reduce((a, b) => a + b, 0);
  const basins = members.map((position, i) => {
    const normal = baseline.reduce((sum, entry) => sum + entry.row[i], 0) / baseline.length;
    const value = latest.row[i];
    const anomaly = value - normal;
    return {
      id: String(index.ids[position]), area: area[i], value, normal, anomaly,
      percent: extensive && normal > 1 ? anomaly / normal * 100 : null,
      contribution: area[i] / total * anomaly,
    };
  });
  const catchment = {
    value: basins.reduce((sum, b) => sum + b.value * b.area, 0) / total,
    normal: basins.reduce((sum, b) => sum + b.normal * b.area, 0) / total,
  };
  catchment.anomaly = catchment.value - catchment.normal;
  catchment.percent = extensive && catchment.normal > 1 ? catchment.anomaly / catchment.normal * 100 : null;

  const groups = new Map();
  for (const basin of basins) {
    const key = String(pfafById.get(basin.id) ?? basin.id).slice(0, 7);
    const group = groups.get(key) || { key, area: 0, value: 0, normal: 0, contribution: 0, basins: 0 };
    group.area += basin.area; group.value += basin.value * basin.area; group.normal += basin.normal * basin.area;
    group.contribution += basin.contribution; group.basins += 1;
    groups.set(key, group);
  }
  const grouped = [...groups.values()].map(group => {
    const value = group.value / group.area, normal = group.normal / group.area;
    return { key: group.key, basins: group.basins, area: group.area, areaShare: group.area / total,
      value, normal, anomaly: value - normal,
      percent: extensive && normal > 1 ? (value - normal) / normal * 100 : null,
      contribution: group.contribution };
  }).sort((a, b) => b.contribution - a.contribution);
  return { waterYear: latest.year, baseline: [baseline[0].year, baseline.at(-1).year], extensive,
    catchment, basins, groups: grouped };
}

/**
 * Winter precipitation against the snow it built, water year by water year.
 *
 * `precipitation` and `snow` are the catchment's monthly rows (year, month, value).
 * Winter is October to March; the snowpack is the largest monthly SWE of the water
 * year. Their ratio says how much of a winter's precipitation stood as snow at the
 * peak, and a winter wetter than normal with a snowpack below normal is the one that
 * fell as rain - wet now, with less stored for summer.
 */
export function snowSeasons(precipitation, snow, { minimumYears = 10 } = {}) {
  const byKey = rows => new Map(rows.filter(row => Number.isFinite(row.value)).map(row => [row.year * 12 + row.month, row.value]));
  const rain = byKey(precipitation), swe = byKey(snow);
  const years = [...new Set(precipitation.map(row => (row.month >= 10 ? row.year + 1 : row.year)))].sort((a, b) => a - b);
  const seasons = [];
  for (const year of years) {
    const winter = [10, 11, 12, 1, 2, 3].map(month => rain.get((month >= 10 ? year - 1 : year) * 12 + month));
    const pack = Array.from({ length: 12 }, (_, i) => {
      const month = ((i + 9) % 12) + 1;
      return swe.get((month >= 10 ? year - 1 : year) * 12 + month);
    });
    if (winter.some(v => v === undefined) || pack.some(v => v === undefined)) continue;
    const winterPrecipitation = winter.reduce((a, b) => a + b, 0);
    const peak = Math.max(...pack);
    const peakMonth = ((pack.indexOf(peak) + 9) % 12) + 1;
    // Snow still lying at the end of the previous September. TerraClimate's snow model
    // has no glaciers, so on ice it carries snow from year to year: that store is not
    // this winter's snow.
    const carryOver = swe.get((year - 1) * 12 + 9) ?? null;
    seasons.push({ waterYear: year, winterPrecipitation, peakSwe: peak, peakMonth, carryOver,
      snowShare: winterPrecipitation > 0 ? peak / winterPrecipitation : null });
  }
  if (seasons.length < minimumYears) return null;
  const mean = key => seasons.reduce((sum, s) => sum + s[key], 0) / seasons.length;
  const normal = { winterPrecipitation: mean('winterPrecipitation'), peakSwe: mean('peakSwe') };
  // A category needs a stated rule, not a feeling for "near normal": each winter is
  // placed in the lowest, middle or highest third of the years this record holds,
  // for precipitation and for the snowpack separately. A peak 21% below the mean
  // that ranks in the lowest third is called below normal, whatever the percentage.
  const third = (value, key) => {
    const below = seasons.filter(s => s[key] < value).length, n = seasons.length;
    const rank = (below + 0.5 * seasons.filter(s => s[key] === value).length) / n;
    return rank < 1 / 3 ? 'below' : rank > 2 / 3 ? 'above' : 'near';
  };
  const rows = seasons.map(season => {
    const rainAnomaly = normal.winterPrecipitation > 0 ? (season.winterPrecipitation / normal.winterPrecipitation - 1) * 100 : null;
    const snowAnomaly = normal.peakSwe > 1 ? (season.peakSwe / normal.peakSwe - 1) * 100 : null;
    const rainClass = third(season.winterPrecipitation, 'winterPrecipitation');
    const snowClass = third(season.peakSwe, 'peakSwe');
    const pct = v => `${Math.abs(Math.round(v))}% ${v >= 0 ? 'above' : 'below'} average`;
    const statement = rainAnomaly === null || snowAnomaly === null ? null
      : `Winter precipitation was ${pct(rainAnomaly)}, while peak modelled snow storage was ${pct(snowAnomaly)}.`;
    let reading = { below: { below: 'dry winter, low snow storage', near: 'dry winter, snow storage near normal', above: 'dry winter, snow storage held' },
      near: { below: 'near-normal winter, low snow storage', near: 'near-normal winter and snow storage', above: 'near-normal winter, high snow storage' },
      above: { below: 'wet winter, low snow storage - more fell as rain or melted early', near: 'wet winter, snow storage near normal', above: 'wet winter, high snow storage' },
    }[rainClass][snowClass];
    return { ...season, rainAnomaly, snowAnomaly, rainClass, snowClass, statement, reading };
  });
  const carried = seasons.filter(s => s.carryOver !== null);
  const carryShare = carried.length && normal.peakSwe > 1
    ? carried.reduce((sum, s) => sum + s.carryOver, 0) / carried.length / normal.peakSwe : null;
  const carryNote = carryShare !== null && carryShare >= 0.25
    ? `On average ${Math.round(carryShare * 100)}% of the peak snow storage here is snow left from earlier years, `
      + 'mostly on glaciers, where the TerraClimate snow model never melts out. Peak storage and its anomaly '
      + 'therefore mix this winter’s snow with a multi-year store; read them with care.'
    : null;
  return { normal, carryShare, carryNote, baseline: [seasons[0].waterYear, seasons.at(-1).waterYear], rows,
    rule: 'Below, near or above normal means the lowest, middle or highest third of the water years in this record, '
      + 'ranked separately for winter precipitation and peak snow storage.',
    snowDominated: normal.peakSwe > 0.2 * normal.winterPrecipitation };
}

/**
 * The ice draining into a set of basins, from the per-basin glacier context file.
 *
 * Assessment matters as much as the figure: a basin never surveyed is absent, not
 * ice-free, so the surveyed share of the catchment is reported beside the total and
 * the total is a floor wherever that share is below one.
 */
export function glacierSummary(context, basins) {
  if (!context?.basins) return null;
  let area = 0, assessed = 0, ice = 0, glaciers = 0, below = 0, small = 0, first = null, last = null;
  for (const { id, area: km2 } of basins) {
    area += km2;
    const entry = context.basins[String(id)];
    if (!entry) continue;
    assessed += km2;
    const [iceKm2, count, belowKm2, smallKm2, survey] = entry;
    ice += iceKm2 || 0; glaciers += count || 0; below += belowKm2 || 0; small += smallKm2 || 0;
    if (survey) { first = Math.min(first ?? survey[0], survey[0]); last = Math.max(last ?? survey[1], survey[1]); }
  }
  if (!assessed) return { assessedShare: 0, iceKm2: null };
  return { area, assessedShare: assessed / area, iceKm2: ice, iceShare: ice / area, glaciers,
    below4000Km2: below, smallKm2: small, survey: first ? [first, last] : null };
}

/**
 * Land cover over the part of a catchment the land-cover series covers, year by year.
 *
 * The annual 10 m product is reduced only over basins intersecting Uzbekistan, so a
 * mountain catchment is often covered in part; the covered share is returned and
 * every figure describes that part alone. Year-to-year differences in a classified
 * product include classification noise, so change is given from the first to the
 * last year rather than as a trend.
 */
export function landcoverSummary(series, index, basins) {
  if (!series?.basins || !index?.years) return null;
  const classes = index.classes.filter(c => c.name !== 'Clouds');
  let area = 0, covered = 0;
  const totals = index.years.map(() => Object.fromEntries(classes.map(c => [c.code, 0])));
  for (const { id, area: km2 } of basins) {
    area += km2;
    const entry = series.basins[String(id)];
    if (!entry) continue;
    covered += km2;
    index.years.forEach((year, y) => {
      for (const c of classes) totals[y][c.code] += entry.years?.[String(year)]?.[String(c.code)] || 0;
    });
  }
  if (!covered) return { coveredShare: 0 };
  const first = totals[0], last = totals.at(-1);
  const change = classes.map(c => ({ code: c.code, name: c.name, color: c.color, first: first[c.code], last: last[c.code],
    change: last[c.code] - first[c.code] })).filter(c => c.first > 0 || c.last > 0);
  // Below a tenth of the catchment the covered part is a sample, not the catchment.
  return { coveredShare: covered / area, coveredKm2: covered, representative: covered / area >= 0.1,
    years: index.years, classes, totals, change };
}

/** River gauges inside the catchment's basins, with the years their record covers. */
export function gaugesInCatchment(gauges, basins) {
  const polygons = basins.flatMap(feature => polygonsOf(feature.geometry).map(rings => ({ rings, id: String(feature.properties.hybas_id) })));
  const inside = [];
  for (const gauge of gauges) {
    const point = gauge.geometry?.coordinates;
    if (!point) continue;
    const hit = polygons.find(({ rings }) => polygonContains(rings, point));
    if (!hit) continue;
    const p = gauge.properties;
    inside.push({ code: p.code, name: p.name_eng || p.name_ru || p.code, river: p.river, basin: hit.id,
      meanDischarge: p.q_m3s ?? null, hasSeries: !!p.has_ts,
      first: p.ts_start ? String(p.ts_start).slice(0, 4) : null, last: p.ts_end ? String(p.ts_end).slice(0, 4) : null,
      completeMonths: p.n_complete ?? null, source: p.source });
  }
  // The compilation lists some stations twice, once per source; keep the record reaching furthest.
  const byCode = new Map();
  for (const gauge of inside) {
    const kept = byCode.get(gauge.code);
    if (!kept || (gauge.last || '') > (kept.last || '')) byCode.set(gauge.code, gauge);
  }
  return [...byCode.values()].sort((a, b) => (b.last || '').localeCompare(a.last || '') || (b.meanDischarge || 0) - (a.meanDischarge || 0));
}

// Measured flow against catchment precipitation, from
// PIPELINES/build_gauge_precipitation_response.py, joined to the gauges a report found.
export function attachResponse(gauges, response) {
  if (!gauges) return gauges;
  const byCode = new Map((response?.gauges || []).map(g => [String(g.code), g]));
  return gauges.map(gauge => {
    const found = byCode.get(String(gauge.code));
    return found ? { ...gauge, response: { ...found.stats, area: found.area_km2, modelled: found.modelled_runoff || null } } : gauge;
  });
}

const signedRound = value => Math.round(value);

/** One plain sentence on how flow at a gauge has followed its catchment's precipitation. */
export function responseSentence(gauge) {
  const r = gauge?.response;
  if (!r || r.r === null) return null;
  const span = `water years ${r.years[0]}–${r.years[1]} (${r.n} years)`;
  const parts = [];
  if (r.r >= 0.6 && r.elasticity !== null) {
    parts.push(`Over ${span}, flow at ${gauge.name} followed the precipitation on its catchment (r = ${r.r.toFixed(2)}): `
      + `a 10% precipitation shortfall went with about ${signedRound(10 * r.elasticity)}% less flow.`);
  } else if (r.r < 0.3) {
    parts.push(`Over ${span}, flow at ${gauge.name} did not follow the precipitation on its catchment (r = ${r.r.toFixed(2)}): `
      + 'glacier melt, reservoirs or withdrawals shape it more than a single year’s precipitation.');
  } else {
    parts.push(`Over ${span}, flow at ${gauge.name} followed its catchment’s precipitation only loosely (r = ${r.r.toFixed(2)}).`);
  }
  if (r.dry_years === 1) {
    parts.push(`In the one year with precipitation 15% or more below average, flow was ${r.dry_years_with_low_flow ? '' : 'not '}below its median.`);
  } else if (r.dry_years) {
    parts.push(`In ${r.dry_years_with_low_flow} of ${r.dry_years} years with precipitation 15% or more below average, flow was below its median.`);
  }
  if (r.runoff_ratio > 1) {
    parts.push(`Measured flow was ${r.runoff_ratio.toFixed(1)} times the gridded precipitation on the catchment, which cannot be: `
      + 'TerraClimate underestimates precipitation here, so read its precipitation volumes as a lower bound.');
  }
  return parts.join(' ');
}

/** The gauge whose record says most about the catchment: the longest well-correlated one, else the longest. */
export function leadingGauge(gauges) {
  const answered = (gauges || []).filter(g => g.response);
  if (!answered.length) return null;
  const strong = answered.filter(g => g.response.r >= 0.6);
  return (strong.length ? strong : answered).sort((a, b) => b.response.n - a.response.n || b.response.area - a.response.area)[0];
}
