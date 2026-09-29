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
    seasons.push({ waterYear: year, winterPrecipitation, peakSwe: peak, peakMonth,
      snowShare: winterPrecipitation > 0 ? peak / winterPrecipitation : null });
  }
  if (seasons.length < minimumYears) return null;
  const mean = key => seasons.reduce((sum, s) => sum + s[key], 0) / seasons.length;
  const normal = { winterPrecipitation: mean('winterPrecipitation'), peakSwe: mean('peakSwe') };
  const rows = seasons.map(season => {
    const rainAnomaly = normal.winterPrecipitation > 0 ? (season.winterPrecipitation / normal.winterPrecipitation - 1) * 100 : null;
    const snowAnomaly = normal.peakSwe > 1 ? (season.peakSwe / normal.peakSwe - 1) * 100 : null;
    let reading = 'near normal';
    if (rainAnomaly !== null && snowAnomaly !== null) {
      if (rainAnomaly >= 10 && snowAnomaly >= 10) reading = 'wet winter, snowpack built';
      else if (rainAnomaly >= 10 && snowAnomaly < 0) reading = 'wet winter, snowpack below normal - more fell as rain or melted early';
      else if (rainAnomaly <= -10 && snowAnomaly <= -10) reading = 'dry winter, thin snowpack';
      else if (rainAnomaly <= -10 && snowAnomaly >= 0) reading = 'dry winter, snowpack held';
    }
    return { ...season, rainAnomaly, snowAnomaly, reading };
  });
  return { normal, baseline: [seasons[0].waterYear, seasons.at(-1).waterYear], rows,
    snowDominated: normal.peakSwe > 0.2 * normal.winterPrecipitation };
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
  return inside.sort((a, b) => (b.last || '').localeCompare(a.last || '') || (b.meanDischarge || 0) - (a.meanDischarge || 0));
}
