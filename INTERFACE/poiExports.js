import { reportMonthlyCsv } from './poiModel.js';
import { attributesCsv, dictionaryCsv } from './aoiModel.js';
import { MORPHOLOGY_FIELDS } from './catchmentStatisticsModel.js';
import fontUrl from './assets/NotoSans-Regular.ttf?url';

const number = value => value == null ? 'Not available' : Number(value).toLocaleString('en', { maximumFractionDigits: 3 });
export const reportFilename = report => `uzgeodata-location-${report.input.id}-${report.variable}`;
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
  for (const scope of ['local', 'upstream']) {
    const data = report[scope];
    line(scope === 'local' ? 'Local basin summary' : 'Upstream catchment summary (including local)', 14);
    line(`${data.ids.length} basins; ${number(data.areaKm2)} km²`);
    const rows = data.rows.filter(row => row.observed_basins > 0);
    if (rows.length) {
      line(`Available record: ${rows[0].year}-${String(rows[0].month).padStart(2, '0')} to ${rows.at(-1).year}-${String(rows.at(-1).month).padStart(2, '0')}`);
      line('Latest 12 months with observations. Full monthly series are in the CSV/JSON files.');
      for (const row of rows.slice(-12)) {
        line(`${row.year}-${String(row.month).padStart(2, '0')}: mean ${number(row.mean_observed_area)} ${report.meta.unit}; coverage ${number(row.area_coverage_percent)}%; total ${number(row.total_full_catchment)} ${data.total.unit || '(not applicable)'}`, 9);
      }
    } else line('No observations are available for this variable.');
    line(data.total.note, 9);
  }
  if (report.morphology) {
    line('Upstream catchment morphology', 14);
    for (const [key, label, unit] of MORPHOLOGY_FIELDS) line(`${label}: ${number(report.morphology[key])} ${unit}`);
  }
  line('Methods and coverage', 14);
  line(report.method, 9);
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
    'basin-attributes.csv': strToU8(attributesCsv(report.catalogue, report.records)),
    'attribute-dictionary.csv': strToU8(dictionaryCsv(report.catalogue)),
    'README.txt': strToU8(`${report.method}\n\nVariable: ${report.variable} (${report.meta.unit}).\nBasin attributes carry the original encoded HydroATLAS values and project estimates in separate columns; consult attribute-dictionary.csv for units and spatial support. Never sum upstream attribute columns across basins. report.json retains source metadata, coverage, morphology, and all monthly rows.\nGeometry missing for ${report.geometry_missing_ids.length} upstream basin IDs (listed in report.json).\n`),
  };
  return zipSync(files, { level: 6 });
}
