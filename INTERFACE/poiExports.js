import { CONDITION_METHOD, reportMonthlyCsv } from './poiModel.js';
import { CONTINUATION_METHOD, continuationCsv, monthlySeries } from './continuationModel.js';
import { DROUGHT_METHOD, ordinal } from './droughtModel.js';
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
  const [{ jsPDF }, ttf] = await Promise.all([import('jspdf'), reportFont()]);
  const doc = new jsPDF({ putOnlyUsedFonts: true, compress: true });
  doc.addFileToVFS('NotoSans.ttf', ttf);
  doc.addFont('NotoSans.ttf', 'NotoSans', 'normal');
  doc.setFont('NotoSans');
  let y = 20;
  const line = (value, size = 10) => {
    doc.setFontSize(size);
    const text = String(value).replace(/[\u0000-\u001f]/g, ' ');
    for (const part of doc.splitTextToSize(text, 174)) {
      if (y > 276) { doc.addPage(); y = 20; }
      doc.text(part, 18, y); y += size * 0.45 + 1.5;
    }
    y += 2;
  };
  line('UZGEODATA · Location report', 18);
  line(report.name, 14);
  line(`Generated: ${report.generatedAt} | File: ${report.sourceFile}`);
  line(`Match: ${report.match.status}; distance: ${number(report.match.distance_km)} km`);
  line(`Level-12 basin IDs: ${report.match.basin_ids.join(', ')}`);
  line(`Variable: ${report.meta.label} (${report.meta.unit})`, 12);
  line(`Source: ${report.meta.source_release || report.meta.source}`);
  if (report.coverage) {
    line(`Record: ${report.coverage.first} to ${report.coverage.last}`
      + ` · ${report.coverage.observed_months} observed months in a ${report.coverage.frame_months}-month frame`);
  }
  for (const scope of ['local', 'upstream']) {
    const data = report[scope];
    line(scope === 'local' ? 'Local basin summary' : 'Upstream catchment summary (including local)', 14);
    line(`${data.ids.length} basins; ${number(data.areaKm2)} km²`);
    // The latest twelve months of the record continued to the present, each
    // marked observed or estimated: listing the last observed months instead
    // made a report printed in 2026 read as if nothing had happened since 2024.
    const series = monthlySeries(data, report.continuation?.[scope]);
    const observed = new Map(data.rows.map(row => [row.year * 12 + row.month, row]));
    if (series.length) {
      const period = row => `${row.year}-${String(row.month).padStart(2, '0')}`;
      line(`Record ${period(series[0])} to ${period(series.at(-1))}; latest 12 months below, full series in the CSV/JSON files.`);
      for (const row of series.slice(-12)) {
        const source = observed.get(row.year * 12 + row.month);
        line(row.source === 'observed'
          ? `${period(row)}: mean ${number(row.value)} ${report.meta.unit}; coverage ${number(source?.area_coverage_percent)}%; total ${number(source?.total_full_catchment)} ${data.total.unit || '(not applicable)'}`
          : `${period(row)}: ${number(row.value)}${row.errorP90 ? ` ±${number(row.errorP90)}` : ''} ${report.meta.unit}, estimated`, 9);
      }
    } else line('No observations are available for this variable.');
    line(data.total.note, 9);
    conditions(data);
  }
  function conditions(data) {
    const scope = data === report.local ? 'local' : 'upstream';
    const now = report.present?.[scope];
    const trend = data.conditions?.trend;
    if (!now) return;
    const unit = report.meta.unit;
    const estimated = source => (source && source !== 'observed' ? ' (estimated)' : '');
    const error = value => (value ? ` ±${number(value)}` : '');
    const versus = (anomaly, percent) => (percent === null || percent === undefined
      ? `anomaly ${number(anomaly)} ${unit}` : `${Math.round(percent)}% vs normal`);
    line(`Current conditions, ${now.latest}`, 12);
    if (now.baseline) line(`Normals: mean of each calendar month over the observed years ${now.baseline.firstYear}-`
      + `${now.baseline.lastYear}. Observed to ${now.lastObserved}; ${now.estimatedMonths} later months are estimates.`, 9);
    const { month, lastTwelveMonths: twelve, waterYearToDate: toDate } = now;
    const sumUnit = now.extensive ? unit.replace(/ per month$/, '') : `${unit} (mean)`;
    line(`Latest month ${month.period}${estimated(month.source)}: ${number(month.value)}${error(month.errorP90)} ${unit}`
      + `; normal ${number(month.normal)}; ${versus(month.anomaly, month.anomalyPercent)}`
      + `${month.withinError ? `; ${month.standing}` : month.percentile === null ? '' : `; ${ordinal(month.percentile)} percentile (${month.standing})`}`);
    if (twelve) line(`Last 12 months ${twelve.from} to ${twelve.to}: ${number(twelve.value)}${error(twelve.errorBound)} ${sumUnit}; `
      + `${versus(twelve.anomaly, twelve.anomalyPercent)}; ${twelve.estimatedMonths} estimated months`);
    if (toDate) line(`Water year ${toDate.waterYear} so far, ${toDate.from} to ${toDate.to}: ${number(toDate.value)}`
      + `${error(toDate.errorBound)} ${sumUnit}; ${versus(toDate.anomaly, toDate.anomalyPercent)}`
      + `${toDate.percentile === null ? '' : `; ${ordinal(toDate.percentile)} percentile of ${toDate.comparedYears} years (${toDate.standing})`}`);
    if (trend) {
      line(`Trend over the observed record, ${trend.years} complete years: ${trend.direction}`
        + `; Sen slope ${number(trend.slopePerDecade)} ${unit} per decade; Mann-Kendall p = ${number(trend.p)}`);
    } else line('Fewer than ten complete observed years: no trend is reported.', 9);
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
    line('Beyond the observed record · estimated', 14);
    for (const scope of ['local', 'upstream']) {
      const latest = report.continuation[scope]?.latest;
      if (!latest) continue;
      const error = latest.errorP90 === null || latest.errorP90 === undefined ? ''
        : `; held-out p90 error ±${number(latest.errorP90)}`;
      line(`${scope === 'local' ? 'Local basin' : 'Upstream catchment'}: `
        + `${latest.months} estimated months from ${latest.first}. Latest ${latest.year}-`
        + `${String(latest.month).padStart(2, '0')}: ${number(latest.value)} ${latest.unit}`
        + `${latest.normal === null ? '' : `; anomaly ${number(latest.anomaly)} against the observed normal`}`
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
  for (let page = 1; page <= pages; page++) { doc.setPage(page); doc.setFontSize(8); doc.text(`uzgeodata.uz · ${page} / ${pages}`, 18, 289); }
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
