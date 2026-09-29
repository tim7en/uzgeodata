import { CONDITION_METHOD, reportMonthlyCsv } from './poiModel.js';
import { CONTINUATION_METHOD, continuationCsv, monthlySeries } from './continuationModel.js';
import { DROUGHT_METHOD, ordinal } from './droughtModel.js';
import { baselineNote, ERROR_BOUND_NOTE, trendBasis, trendUnit } from './reportTerms.js';
import { attributesCsv, dictionaryCsv } from './aoiModel.js';
import { MORPHOLOGY_FIELDS } from './catchmentStatisticsModel.js';
import fontUrl from './assets/NotoSans-Regular.ttf?url';

const number = value => value == null ? 'Not available' : Number(value).toLocaleString('en', { maximumFractionDigits: 3 });
export const reportFilename = report => `uzgeodata-location-${report.input.id}-${report.variable}`;
/**
 * On a phone a download link opens the blob in a tab at best; the share sheet is
 * how a file reaches a messenger, mail or Files. It is offered only on touch
 * devices that can share files, and anything short of a completed share other
 * than the reader cancelling falls back to the ordinary download - including a
 * share refused because generating the PDF outlasted the tap that asked for it.
 */
export async function shareOrSaveFile(name, data, type) {
  const file = typeof File === 'function' ? new File([data], name, { type }) : null;
  const touch = window.matchMedia?.('(pointer: coarse)').matches;
  if (touch && file && navigator.canShare?.({ files: [file] })) {
    try { await navigator.share({ files: [file], title: name }); return; } catch (cause) {
      if (cause?.name === 'AbortError') return;
    }
  }
  saveFile(name, data, type);
}

export function saveFile(name, data, type) {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const link = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

let font;
async function reportFont() {
  if (!font) {
    const response = await fetch(fontUrl);
    if (!response.ok) throw Error('The report font could not load. Please retry.');
    const bytes = new Uint8Array(await response.arrayBuffer());
    let binary = '';
    for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
    font = btoa(binary);
  }
  return font;
}

export async function reportPdf(report) {
  const [{ jsPDF }, ttf, { reportFigures }] = await Promise.all([import('jspdf'), reportFont(), import('./reportFigures.js')]);
  const figures = await reportFigures(report);
  const doc = new jsPDF({ putOnlyUsedFonts: true, compress: true });
  doc.addFileToVFS('NotoSans.ttf', ttf);
  doc.addFont('NotoSans.ttf', 'NotoSans', 'normal');
  doc.setFont('NotoSans');
  doc.setProperties({ title: `${report.name} · Basin & upstream report`, author: 'UzGeoData',
    subject: `${report.meta.label}: local and upstream conditions, maps and forecast`, creator: 'UzGeoData basin atlas' });
  let y = 30;
  const newPage = () => { doc.addPage(); y = 30; };
  const line = (value, size = 10) => {
    if (size >= 12 && y > 245) newPage();
    doc.setFontSize(size);
    doc.setTextColor(size >= 12 ? '#163b49' : '#344c57');
    const text = String(value).replace(/[\u0000-\u001f]/g, ' ');
    for (const part of doc.splitTextToSize(text, 174)) {
      if (y > 274) { newPage(); doc.setFontSize(size); }
      doc.text(part, 18, y); y += size * 0.45 + 1.5;
    }
    y += 2;
  };
  let figureNumber = 0;
  const figure = (item, height) => {
    const caption = `Figure ${++figureNumber}. ${item.caption}`;
    doc.setFontSize(9);
    const lines = doc.splitTextToSize(caption, 174);
    const needed = height + lines.length * 5.55 + 19;
    if (y + needed > 274) newPage();
    if (item.title) line(item.title, 12);
    if (item.image) doc.addImage(item.image, 'PNG', 18, y, 174, height);
    y += height + 5;
    line(caption, 9);
  };

  line('BASIN & UPSTREAM REPORT', 22);
  line(report.name, 14);
  line(`${report.meta.label} · ${report.meta.unit}`, 11);
  line(`Issued ${report.generatedAt.slice(0, 10)} · ${report.meta.source_release || report.meta.source}`, 9);
  if (figures.map.image) figure({ image: figures.map.image, caption: figures.map.note }, 109.4);
  else line(figures.map.note, 10);
  line('Catchment at a glance', 14);
  line(`Local: ${number(report.local.areaKm2)} km² · ${report.local.ids.length} basin(s). `
    + `Upstream including local: ${number(report.upstream.areaKm2)} km² · ${report.upstream.ids.length} basin(s).`);
  if (report.coverage) line(`Historical gridded data (${report.meta.source_release || report.meta.source}): `
    + `${report.coverage.first}–${report.coverage.last}. These are modelled grids built from stations, satellites and `
    + 'reanalysis, not rain-gauge readings at this basin. Later months are provisional model-derived estimates from '
    + 'ERA5-Land and are marked so; seasonal outlooks are forecasts.', 9);
  const baseline = report.present?.local?.baseline;
  if (baseline) line(baselineNote(baseline.firstYear, baseline.lastYear), 9);
  if (report.geometry_missing_ids.length) line(`Map coverage: ${report.geometry_missing_ids.length} upstream basins have statistics but no display boundary.`, 9);

  for (const section of figures.series) {
    newPage();
    line(section.scope === 'local' ? '01 / LOCAL BASIN' : '02 / UPSTREAM CATCHMENT', 18);
    line(`${report.meta.label} · ${report.meta.unit}`, 11);
    line('Monthly values against the seasonal normal of the gridded record. Both time windows are included regardless of the on-screen chart selection.', 9);
    if (!section.figures.length) line('No monthly values are available for this scope.');
    for (const item of section.figures) figure(item, 57.2);
    if (section.scope === 'upstream' && report.continuation?.upstreamWithheld) {
      line('Upstream provisional estimates are withheld because the matched catchments overlap. Only the gridded upstream record is shown.', 9);
    }
  }
  if (figures.drought.length) {
    newPage(); line('03 / DROUGHT HISTORY', 18);
    line('Water-year precipitation as SPI-12, fitted on 1991–2020 - a different baseline from the monthly normals above. Local and upstream records are shown separately.', 10);
    for (const item of figures.drought) figure(item, 53.4);
  }
  for (let i = 0; i < figures.seasonal.length; i++) {
    if (i % 2 === 0) {
      newPage(); line('04 / SEASONAL OUTLOOK', 18);
      line('Grey bars indicate no demonstrated forecast skill: use the normal range. Coloured bars indicate useful historical skill. Probabilities refer to below-, near- and above-normal conditions.', 9);
    }
    const section = figures.seasonal[i];
    line(section.title, 12); line(section.subtitle, 9);
    for (const { entry, variable, image } of section.entries) {
      const unit = variable === 'ppt' ? 'mm' : '°C';
      const f = entry.forecast;
      figure({ image, title: variable === 'ppt' ? 'Precipitation' : 'Mean temperature',
        caption: `Median ${number(f.median)} ${unit}; 80% range ${number(f.p10)}–${number(f.p90)} ${unit}; normal ${number(f.normal)} ${unit}. `
          + (variable === 'ppt' ? `Drought-level probability ${Math.round(f.dry_probability * 100)}%. ` : '')
          + (entry.skill.useful ? `RPSS ${number(entry.skill.rpss)} (${entry.skill.years} hindcast years).`
            : 'No demonstrated skill; use climatology.') }, 18);
    }
    if (i % 2 === 1 || i === figures.seasonal.length - 1) line('Applies to the named level-7 basin or zone. Precipitation and temperature only; not a river-flow forecast.', 8);
  }
  if (figures.forecastMissing) { newPage(); line('Seasonal outlook', 18); line('No seasonal forecast could be loaded for this location at export time.'); }
  upstreamSection(report.upstreamInsights, figures.attribution);
  newPage(); line('05 / STATISTICS & METHODS', 18);
  line(report.name, 14);
  line(`Generated: ${report.generatedAt} | File: ${report.sourceFile}`);
  line(`Match: ${report.match.status}; distance: ${number(report.match.distance_km)} km`);
  line(`Level-12 basin IDs: ${report.match.basin_ids.join(', ')}`);
  line(`Variable: ${report.meta.label} (${report.meta.unit})`, 12);
  line(`Source: ${report.meta.source_release || report.meta.source}`);
  if (report.coverage) {
    line(`Record: ${report.coverage.first} to ${report.coverage.last}`
      + ` · ${report.coverage.observed_months} months of gridded data in a ${report.coverage.frame_months}-month frame`);
  }
  for (const scope of ['local', 'upstream']) {
    const data = report[scope];
    line(scope === 'local' ? 'Local basin summary' : 'Upstream catchment summary (including local)', 14);
    line(`${data.ids.length} basins; ${number(data.areaKm2)} km²`);
    // The latest twelve months of the record continued to the present, each
    // marked gridded or provisional: listing the last gridded months instead
    // made a report printed in 2026 read as if nothing had happened since 2024.
    const series = monthlySeries(data, report.continuation?.[scope]);
    const observed = new Map(data.rows.map(row => [row.year * 12 + row.month, row]));
    if (series.length) {
      const period = row => `${row.year}-${String(row.month).padStart(2, '0')}`;
      line(`Record ${period(series[0])} to ${period(series.at(-1))}; latest 12 months below, full series in the CSV/JSON files.`);
      for (const row of series.slice(-12)) {
        const source = observed.get(row.year * 12 + row.month);
        line(row.source === 'observed'
          ? `${period(row)}: mean ${number(row.value)} ${report.meta.unit}; coverage ${number(source?.area_coverage_percent)}%`
            + (data.total.unit ? `; ${data.total.label.toLowerCase()} ${number(source?.total_full_catchment)} ${data.total.unit}` : '')
          : `${period(row)}: ${number(row.value)}${row.errorP90 ? ` ±${number(row.errorP90)}` : ''} ${report.meta.unit}, provisional estimate`, 9);
      }
    } else line('No values are available for this variable.');
    line(data.total.note, 9);
    conditions(data);
  }
  function conditions(data) {
    const scope = data === report.local ? 'local' : 'upstream';
    const now = report.present?.[scope];
    const trend = data.conditions?.trend;
    if (!now) return;
    const unit = report.meta.unit;
    const estimated = source => (source && source !== 'observed' ? ' (provisional estimate)' : '');
    const error = value => (value ? ` ±${number(value)}` : '');
    const versus = (anomaly, percent) => (percent === null || percent === undefined
      ? `anomaly ${number(anomaly)} ${unit}` : `${Math.round(percent)}% vs normal`);
    line(`Current conditions, ${now.latest}`, 12);
    if (now.baseline) line(`Normals: mean of each calendar month over ${now.baseline.firstYear}-${now.baseline.lastYear} `
      + `of the gridded record. Gridded data to ${now.lastObserved}; ${now.estimatedMonths} later months are provisional estimates.`, 9);
    const { month, lastTwelveMonths: twelve, waterYearToDate: toDate } = now;
    const sumUnit = now.extensive ? unit.replace(/ per month$/, '') : `${unit} (mean)`;
    line(`Latest month ${month.period}${estimated(month.source)}: ${number(month.value)}${error(month.errorP90)} ${unit}`
      + `; normal ${number(month.normal)}; ${versus(month.anomaly, month.anomalyPercent)}`
      + `${month.withinError ? `; ${month.standing}` : month.percentile === null ? '' : `; ${ordinal(month.percentile)} percentile (${month.standing})`}`);
    if (twelve) line(`Last 12 months ${twelve.from} to ${twelve.to}: ${number(twelve.value)}${error(twelve.errorBound)} ${sumUnit}; `
      + `${versus(twelve.anomaly, twelve.anomalyPercent)}; ${twelve.estimatedMonths} provisional months`
      + `${twelve.errorBound ? ' (± is a conservative bound, see below)' : ''}`);
    if (toDate) line(`Water year ${toDate.waterYear} so far, ${toDate.from} to ${toDate.to}: ${number(toDate.value)}`
      + `${error(toDate.errorBound)} ${sumUnit}; ${versus(toDate.anomaly, toDate.anomalyPercent)}`
      + `${toDate.percentile === null ? '' : `; ${ordinal(toDate.percentile)} percentile of ${toDate.comparedYears} years (${toDate.standing})`}`);
    if (trend) {
      line(`Trend in ${trendBasis(now.extensive)} over the gridded record, ${trend.years} complete years: ${trend.direction}`
        + `; Sen slope ${number(trend.slopePerDecade)} ${trendUnit(unit, now.extensive)}; Mann-Kendall p = ${number(trend.p)}`);
    } else line('Fewer than ten complete years of gridded data: no trend is reported.', 9);
    if (twelve?.errorBound || toDate?.errorBound) line(ERROR_BOUND_NOTE, 9);
  }

  function upstreamSection(insights, map) {
    if (!insights || (!insights.attribution && !insights.snow && !insights.gauges)) return;
    newPage(); line('UPSTREAM IN DETAIL', 18);
    const a = insights.attribution;
    if (a) {
      const unit = a.extensive ? insights.unit.replace(/ per month$/, '') : insights.unit;
      const signed = v => `${v > 0 ? '+' : ''}${number(v)}`;
      const pct = v => `${v > 0 ? '+' : ''}${Math.round(v)}%`;
      const mm = v => `${v > 0 ? '+' : ''}${Math.round(v * 10) / 10}`;
      line(`Where the anomaly came from · water year ${a.waterYear}`, 14);
      line(`Upstream ${insights.label}: ${number(a.catchment.value)} ${unit} against a ${a.baseline[0]}–${a.baseline[1]} normal of `
        + `${number(a.catchment.normal)} (${a.catchment.percent === null ? `${signed(a.catchment.anomaly)} ${unit}` : pct(a.catchment.percent)}). `
        + 'Each sub-basin contributes its area share times its own anomaly, so the contributions add up to the catchment figure.', 9);
      if (map?.image) figure({ image: map.image, caption: map.note }, 109.4);
      const describe = g => `Level-7 basin ${g.key}: ${Math.round(g.areaShare * 100)}% of the area, own anomaly `
        + `${g.percent === null ? `${signed(g.anomaly)} ${unit}` : pct(g.percent)}, contribution ${mm(g.contribution)} ${a.extensive ? 'mm' : unit}`;
      const wetter = a.groups.filter(g => g.contribution > 0).slice(0, 5);
      const drier = a.groups.filter(g => g.contribution < 0).slice(-5).reverse();
      if (wetter.length) { line(a.extensive ? 'Pushed it wetter' : 'Pushed it warmer', 11); wetter.forEach(g => line(describe(g), 9)); }
      if (drier.length) { line(a.extensive ? 'Pushed it drier' : 'Pushed it colder', 11); drier.forEach(g => line(describe(g), 9)); }
    }
    const snow = insights.snow;
    if (snow) {
      line('Snow storage upstream', 14);
      line(`October–March precipitation against the peak monthly snow water equivalent it built, each against its `
        + `${snow.baseline[0]}–${snow.baseline[1]} mean. Snow water equivalent is TerraClimate v1.1’s modelled snowpack, not a measurement.`, 9);
      for (const r of snow.rows.slice(-8).reverse()) {
        line(`WY ${r.waterYear}: winter precipitation ${number(r.winterPrecipitation)} mm`
          + `${r.rainAnomaly === null ? '' : ` (${r.rainAnomaly > 0 ? '+' : ''}${Math.round(r.rainAnomaly)}%)`}; peak snowpack `
          + `${number(r.peakSwe)} mm${r.snowAnomaly === null ? '' : ` (${r.snowAnomaly > 0 ? '+' : ''}${Math.round(r.snowAnomaly)}%)`} — ${r.reading}.`, 9);
      }
    }
    const gauges = insights.gauges;
    if (gauges) {
      line('River gauges in this catchment', 14);
      if (!gauges.length) line('No gauge of the CA-discharge compilation lies in these basins; precipitation here cannot yet be set against measured flow.', 9);
      for (const g of gauges.slice(0, 10)) {
        line(`${g.name} (${g.code})${g.river ? `, ${g.river}` : ''}: ${g.first && g.last ? `record ${g.first}–${g.last}` : 'no monthly series'}`
          + `${g.meanDischarge === null ? '' : `, mean ${number(g.meanDischarge)} m³/s`}.`, 9);
      }
      line('Gauge series are not yet joined to these reports; runoff figures in the atlas are modelled generation, not measured discharge.', 9);
    }
  }

  function droughtSection(drought) {
    if (!drought) return;
    line('Drought and outlook', 14);
    for (const [scope, title] of [['local', 'This basin'], ['upstream', 'Everything upstream (headwater supply)']]) {
      const reading = drought[scope];
      if (!reading) continue;
      const { outlook, toDate, chance } = reading;
      const { last, recent, early, afterDry, any, trend } = outlook;
      const pct = value => (value === null || value === undefined ? '-' : `${Math.round(value * 100)}%`);
      line(title, 12);
      if (toDate) line(`Water year ${toDate.waterYear} so far (${toDate.from} to ${toDate.to}): ${number(toDate.value)} mm, `
        + `${toDate.anomalyPercent === null ? '-' : Math.round(toDate.anomalyPercent)}% vs normal${toDate.percentile === null ? ''
          : `, ${ordinal(toDate.percentile)} percentile of ${toDate.comparedYears} years`}${toDate.dry ? ' - drought-level dry' : ''}.`);
      line(`Last complete water year ${last.year}: SPI-12 ${number(last.spi)}`
        + `${last.severe ? ', severe drought' : last.dry ? ', drought' : ', not a drought year'}.`);
      line(`Drought years ${recent.from}-${recent.to}: ${recent.dry} of ${recent.years} (${pct(recent.dryShare)}), `
        + `${recent.severe} severe; ${early.from}-${early.to}: ${early.dry} of ${early.years} (${pct(early.dryShare)}).`);
      line(`After a drought year the next was dry in ${afterDry.dry} of ${afterDry.years}; any year: ${pct(any.share)}.`);
      if (chance) line(chance.sparse
        ? `Chance of a drought year in WY ${chance.forWaterYear}: too few comparable years to give one.`
        : `Chance of a drought year in WY ${chance.forWaterYear}: ${pct(chance.share)} (${chance.dryYears} of ${chance.years} `
          + `years after a ${chance.dry ? 'dry' : 'non-drought'} year), against ${pct(chance.baseShare)} in any year. `
          + 'A historical frequency, not a forecast.');
      if (trend) line(`Trend ${trend.from}-${trend.to}: ${trend.direction}; ${number(trend.pointsPerDecade)} points of `
        + `normal per decade; p = ${number(trend.p)}.`);
    }
    line(DROUGHT_METHOD, 9);
  }

  if (report.morphology) {
    line('Upstream catchment morphology', 14);
    for (const [key, label, unit] of MORPHOLOGY_FIELDS) line(`${label}: ${number(report.morphology[key])} ${unit}`);
  }
  droughtSection(report.drought);
  if (report.continuation) {
    line('Beyond the gridded record · provisional estimates', 14);
    for (const scope of ['local', 'upstream']) {
      const latest = report.continuation[scope]?.latest;
      if (!latest) continue;
      const error = latest.errorP90 === null || latest.errorP90 === undefined ? ''
        : `; held-out p90 error ±${number(latest.errorP90)}`;
      line(`${scope === 'local' ? 'Local basin' : 'Upstream catchment'}: `
        + `${latest.months} provisional months from ${latest.first}. Latest ${latest.year}-`
        + `${String(latest.month).padStart(2, '0')}: ${number(latest.value)} ${latest.unit}`
        + `${latest.normal === null ? '' : `; anomaly ${number(latest.anomaly)} against the gridded-record normal`}`
        + `${error}${latest.withinError ? '; within the model error of normal' : ''}`);
    }
    line(CONTINUATION_METHOD, 9);
  }
  line('Methods and coverage', 14);
  line(report.method, 9);
  line(CONDITION_METHOD, 9);
  if (report.geometry_missing_ids.length) line(`${report.geometry_missing_ids.length} upstream basins have statistics but no display geometry.`, 9);
  if (report.morphology?.traced_area_km2 < report.morphology?.reported_upstream_area_km2 * 0.95) line('The traced network covers less than 95% of the reported upstream area. These results describe only the published network.');
  for (const note of report.morphology_notes) line(note, 9);
  if (report.variable === 'snw_pc_s') line('Snow-cover records are not suitable for trend analysis.', 9);
  line('Source records', 14);
  for (const source of report.provenance) line(JSON.stringify(source), 8);
  line('The downloadable ZIP includes the input geometry, basin boundaries, full monthly statistics, basin attributes, and source metadata.', 9);
  const pages = doc.getNumberOfPages();
  for (let page = 1; page <= pages; page++) {
    doc.setPage(page);
    doc.setDrawColor('#087e98'); doc.setLineWidth(0.7); doc.line(18, 15, 192, 15);
    doc.setFontSize(8); doc.setTextColor('#163b49'); doc.text('UZGEODATA / BASIN ATLAS', 18, 12);
    doc.setTextColor('#617782'); doc.text(report.generatedAt.slice(0, 10), 192, 12, { align: 'right' });
    doc.setDrawColor('#dfe7eb'); doc.setLineWidth(0.2); doc.line(18, 282, 192, 282);
    doc.setFontSize(8); doc.text('uzgeodata.uz · Gridded record / Provisional estimate / Forecast', 18, 289);
    doc.text(`${page} / ${pages}`, 192, 289, { align: 'right' });
  }
  return new Uint8Array(doc.output('arraybuffer'));
}

/** The water-year records the drought section was read from, one row a year. */
function droughtCsv(drought) {
  const lines = [];
  for (const scope of ['local', 'upstream']) {
    const record = drought[scope]?.record;
    if (!record) continue;
    if (!lines.length) lines.push(['reading', 'basin_id', ...record.fields].join(','));
    for (const row of record.rows) lines.push([scope, record.basin_id, ...row.map(value => value ?? '')].join(','));
  }
  return `${lines.join('\n')}\n`;
}

export async function reportZip(report) {
  const { zipSync, strToU8 } = await import('fflate');
  const json = data => strToU8(JSON.stringify(data, null, 2));
  const files = {
    'report.pdf': await reportPdf(report),
    'report.json': json(report),
    'input.geojson': json(report.input),
    'matched-basins.geojson': json(report.local_geometry),
    'upstream-basins.geojson': json(report.upstream_geometry),
    'monthly-statistics.csv': strToU8(reportMonthlyCsv(report)),
    ...(report.continuation ? { 'continuation-estimates.csv': strToU8(
      ['support,product,unit,year,month,value,coverage_fraction,holdout_abs_error_p90']
        .concat(['local', 'upstream'].flatMap(scope => continuationCsv(
          { estimated: report.continuation[scope]?.estimated, direct: report.continuation[scope]?.direct }, scope,
        ).map(row => row.join(','))))
        .join('\n')) } : {}),
    ...(report.drought ? { 'drought-water-years.csv': strToU8(droughtCsv(report.drought)) } : {}),
    'basin-attributes.csv': strToU8(attributesCsv(report.catalogue, report.records)),
    'attribute-dictionary.csv': strToU8(dictionaryCsv(report.catalogue)),
    'README.txt': strToU8(`${report.method}\n\nVariable: ${report.variable} (${report.meta.unit}).\nBasin attributes carry the original encoded HydroATLAS values and project estimates in separate columns; consult attribute-dictionary.csv for units and spatial support. Never sum upstream attribute columns across basins. report.json retains source metadata, coverage, morphology, and all monthly rows.\nGeometry missing for ${report.geometry_missing_ids.length} upstream basin IDs (listed in report.json).\n`),
  };
  return zipSync(files, { level: 6 });
}
