import { monthlySeries } from './continuationModel.js';
import { chartWindow, monthlyNormals } from './poiModel.js';
import { BASEMAPS } from './mapViewModel.js';
import { forecastUnits, readForecast } from './seasonalModel.js';

const INK = '#163b49', TEAL = '#087e98', GOLD = '#b46b16', GREY = '#798a92';
const W = 1400;
const fmt = value => Number(value).toLocaleString('en', { maximumFractionDigits: 1 });
const period = row => `${row.year}-${String(row.month).padStart(2, '0')}`;

function surface(height) {
  const canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = height;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, W, height);
  ctx.font = '24px Arial'; ctx.fillStyle = INK;
  return { canvas, ctx };
}

// Normalized Web Mercator: the same projection used by the report's tile layer.
export function project([longitude, latitude]) {
  const lat = Math.max(-85.051129, Math.min(85.051129, latitude)) * Math.PI / 180;
  return [(longitude + 180) / 360, (1 - Math.log(Math.tan(Math.PI / 4 + lat / 2)) / Math.PI) / 2];
}

function coordinates(geometry) {
  if (!geometry) return [];
  if (geometry.type === 'GeometryCollection') return geometry.geometries.flatMap(coordinates);
  const visit = value => typeof value?.[0] === 'number' ? [value] : (value || []).flatMap(visit);
  return visit(geometry.coordinates);
}

export function mapFrame(report, width = W, height = 880) {
  const points = [...report.upstream_geometry.features, ...report.local_geometry.features, report.input]
    .flatMap(feature => coordinates(feature.geometry)).map(project);
  if (!points.length) return null;
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  // Reduce rather than spread: a large upstream network has millions of vertices.
  const minX = xs.reduce((a, b) => Math.min(a, b), Infinity), maxX = xs.reduce((a, b) => Math.max(a, b), -Infinity);
  const minY = ys.reduce((a, b) => Math.min(a, b), Infinity), maxY = ys.reduce((a, b) => Math.max(a, b), -Infinity);
  const zoom = Math.max(0, Math.min(13, Math.floor(Math.log2(Math.min(
    (width - 160) / (256 * Math.max(maxX - minX, 1e-8)),
    (height - 160) / (256 * Math.max(maxY - minY, 1e-8)),
  )))));
  const scale = 256 * 2 ** zoom;
  return { zoom, scale, left: (minX + maxX) * scale / 2 - width / 2,
    top: (minY + maxY) * scale / 2 - height / 2, centerY: (minY + maxY) / 2 };
}

async function basinMap(report, { upstreamFill = null, note = null } = {}) {
  const height = 880, frame = mapFrame(report, W, height);
  if (!frame) return { image: null, note: 'No display geometry is available for this report.' };
  const { canvas, ctx } = surface(height);
  const { zoom, scale, left, top } = frame;
  ctx.fillStyle = '#eaf0f1'; ctx.fillRect(0, 0, W, height);
  const base = BASEMAPS.find(item => item.id === 'terrain');
  const tiles = [];
  for (let x = Math.floor(left / 256); x <= Math.floor((left + W) / 256); x++) {
    for (let y = Math.floor(top / 256); y <= Math.floor((top + height) / 256); y++) {
      if (y >= 0 && y < 2 ** zoom) tiles.push({ x, y });
    }
  }
  let missing = 0;
  const queue = tiles.values();
  await Promise.all(Array.from({ length: 6 }, async () => {
    for (const tile of queue) {
      try {
        const url = base.url.replace('{z}', zoom).replace('{x}', ((tile.x % 2 ** zoom) + 2 ** zoom) % 2 ** zoom).replace('{y}', tile.y);
        const response = await fetch(url, { signal: AbortSignal.timeout(8000) });
        if (!response.ok) throw Error('Tile unavailable');
        const bitmap = await createImageBitmap(await response.blob());
        ctx.drawImage(bitmap, tile.x * 256 - left, tile.y * 256 - top, 256, 256);
        bitmap.close();
      } catch { missing++; }
    }
  }));
  const xy = point => { const p = project(point); return [p[0] * scale - left, p[1] * scale - top]; };
  function draw(geometry, stroke, fill, weight) {
    if (!geometry) return;
    if (geometry.type === 'GeometryCollection') { geometry.geometries.forEach(g => draw(g, stroke, fill, weight)); return; }
    if (geometry.type === 'Point') {
      const [x, y] = xy(geometry.coordinates);
      ctx.beginPath(); ctx.arc(x, y, 8, 0, 2 * Math.PI); ctx.fillStyle = '#fff'; ctx.fill();
      ctx.strokeStyle = stroke; ctx.lineWidth = 4; ctx.stroke(); return;
    }
    const polygons = geometry.type === 'MultiPolygon' ? geometry.coordinates
      : geometry.type === 'Polygon' ? [geometry.coordinates] : [];
    for (const polygon of polygons) {
      ctx.beginPath();
      for (const ring of polygon) {
        ring.forEach((point, i) => { const [x, y] = xy(point); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
        ctx.closePath();
      }
      if (fill) { ctx.fillStyle = fill; ctx.fill('evenodd'); }
      ctx.strokeStyle = stroke; ctx.lineWidth = weight; ctx.stroke();
    }
  }
  report.upstream_geometry.features.forEach(f => draw(f.geometry, upstreamFill ? '#4b5d64' : '#087fba',
    upstreamFill ? upstreamFill(f) : '#148fc12b', upstreamFill ? 0.3 : 0.4));
  report.local_geometry.features.forEach(f => draw(f.geometry, '#ad5400', '#ed9b3b70', 3));
  draw(report.input.geometry, '#6c34a0', null, 3);
  // North is up in Web Mercator; the scale is measured at the map centre.
  ctx.fillStyle = '#ffffffee'; ctx.fillRect(W - 85, 20, 60, 90);
  ctx.fillStyle = INK; ctx.textAlign = 'center'; ctx.fillText('N', W - 55, 47);
  ctx.beginPath(); ctx.moveTo(W - 55, 58); ctx.lineTo(W - 68, 95); ctx.lineTo(W - 55, 86); ctx.lineTo(W - 42, 95); ctx.closePath(); ctx.fill();
  const lat = Math.atan(Math.sinh(Math.PI * (1 - 2 * frame.centerY)));
  const metresPerPixel = 40075016.686 * Math.cos(lat) / scale;
  const target = metresPerPixel * 200;
  const power = 10 ** Math.floor(Math.log10(target));
  const metres = [1, 2, 5].map(v => v * power).filter(v => v <= target).at(-1) || power;
  const length = metres / metresPerPixel;
  ctx.fillStyle = '#ffffffed'; ctx.fillRect(20, height - 86, length + 40, 66);
  ctx.strokeStyle = INK; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(40, height - 50); ctx.lineTo(40 + length, height - 50); ctx.stroke();
  ctx.fillStyle = INK; ctx.textAlign = 'left'; ctx.fillText(metres >= 1000 ? `${fmt(metres / 1000)} km` : `${fmt(metres)} m`, 40, height - 28);
  if (note) return { image: canvas.toDataURL('image/png'), note: `${note}${missing ? ` ${missing} basemap tiles unavailable.` : ''}` };
  return { image: canvas.toDataURL('image/png'),
    note: `Orange: local basins. Blue: upstream catchment, including local basins. Purple: input location. North up; scale at map centre. Shaded relief © Esri.${missing ? ` ${missing} basemap tiles unavailable; boundaries remain accurate.` : ''}` };
}

function axes(ctx, low, high, height) {
  const box = { left: 100, right: W - 25, top: 28, bottom: height - 70 };
  const y = v => box.bottom - (v - low) / (high - low) * (box.bottom - box.top);
  ctx.font = '22px Arial';
  for (let i = 0; i <= 4; i++) {
    const v = low + (high - low) * i / 4;
    ctx.strokeStyle = '#dfe7eb'; ctx.lineWidth = 1; ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(box.left, y(v)); ctx.lineTo(box.right, y(v)); ctx.stroke();
    ctx.fillStyle = GREY; ctx.textAlign = 'right'; ctx.fillText(fmt(v), box.left - 14, y(v) + 7);
  }
  return { ...box, y };
}

function monthlyFigure(report, scope, span) {
  const normals = monthlyNormals(report[scope].rows);
  const rows = chartWindow(monthlySeries(report[scope], report.continuation?.[scope]), normals, span);
  if (!rows.length) return null;
  const height = 460, { canvas, ctx } = surface(height);
  const floor = rows.every(r => r.value >= 0) ? 0 : -Infinity;
  const values = rows.flatMap(r => [r.value, r.normal, r.value + (r.errorP90 || 0), Math.max(floor, r.value - (r.errorP90 || 0))]).filter(Number.isFinite);
  let low = Math.min(...values), high = Math.max(...values);
  if (low === high) { low -= 1; high += 1; }
  const a = axes(ctx, low, high, height), first = rows[0].key, last = rows.at(-1).key;
  const x = key => a.left + (last === first ? .5 : (key - first) / (last - first)) * (a.right - a.left);
  const step = Math.max(1, Math.ceil(rows.length / 7));
  ctx.textAlign = 'center'; ctx.fillStyle = GREY;
  rows.forEach((row, i) => { if (i % step === 0) ctx.fillText(period(row), x(row.key), height - 28); });
  // Separate runs: neither gaps nor the observed/estimated boundary are joined.
  const draw = (pick, color, dashed = false) => {
    ctx.strokeStyle = color; ctx.lineWidth = 3; ctx.setLineDash(dashed ? [9, 6] : []);
    let previous = null;
    for (const row of rows) {
      const value = pick(row);
      if (!Number.isFinite(value)) { previous = null; continue; }
      if (previous && previous.key + 1 === row.key) {
        ctx.beginPath(); ctx.moveTo(x(previous.key), a.y(previous.value)); ctx.lineTo(x(row.key), a.y(value)); ctx.stroke();
      } else { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x(row.key), a.y(value), 3, 0, Math.PI * 2); ctx.fill(); }
      previous = { key: row.key, value };
    }
  };
  ctx.fillStyle = '#e6b87055';
  rows.forEach((row, i) => {
    const next = rows[i + 1];
    if (row.source === 'observed' || !Number.isFinite(row.errorP90)) return;
    const band = [row, next?.source !== 'observed' && next?.key === row.key + 1 && Number.isFinite(next.errorP90) ? next : row];
    ctx.beginPath();
    band.forEach((r, j) => ctx[j ? 'lineTo' : 'moveTo'](x(r.key), a.y(r.value + r.errorP90)));
    [...band].reverse().forEach(r => ctx.lineTo(x(r.key), a.y(Math.max(floor, r.value - r.errorP90))));
    ctx.closePath(); ctx.fill();
  });
  draw(r => r.normal, GREY, true);
  draw(r => r.source === 'observed' ? r.value : null, TEAL);
  draw(r => r.source !== 'observed' ? r.value : null, GOLD, true);
  return { image: canvas.toDataURL('image/png'),
    title: span ? 'Recent conditions · last 36 calendar months' : 'Full monthly record',
    caption: `${period(rows[0])} to ${period(rows.at(-1))} · ${report.meta.unit}. Teal: historical gridded data. Gold: provisional estimate, with held-out p90 error band. Dashed grey: monthly normal${normals ? ` (${normals.firstYear}–${normals.lastYear})` : ''}. Gaps remain unconnected.` };
}

function droughtFigure(reading, scope) {
  const record = reading?.record;
  if (!record) return null;
  const field = name => record.fields.indexOf(name);
  const rows = record.rows.map(r => ({ year: r[field('water_year')], spi: r[field(scope === 'local' ? 'spi12' : 'up_spi12')] })).filter(r => Number.isFinite(r.spi));
  if (!rows.length) return null;
  const height = 430, { canvas, ctx } = surface(height);
  const limit = Math.max(2.5, ...rows.map(r => Math.abs(r.spi)));
  const a = axes(ctx, -limit, limit, height), first = rows[0].year, last = rows.at(-1).year;
  const step = (a.right - a.left) / (last - first + 1);
  for (const row of rows) {
    const x = a.left + (row.year - first) * step;
    ctx.fillStyle = row.spi <= -1 ? '#aa612b' : row.spi >= 1 ? TEAL : '#b5c9d0';
    ctx.fillRect(x + 1, Math.min(a.y(0), a.y(row.spi)), Math.max(1, step - 2), Math.max(1, Math.abs(a.y(row.spi) - a.y(0))));
    if ((row.year - first) % Math.max(1, Math.ceil((last - first + 1) / 8)) === 0) {
      ctx.fillStyle = GREY; ctx.textAlign = 'center'; ctx.fillText(row.year, x + step / 2, height - 28);
    }
  }
  for (const threshold of [-1, -1.5]) {
    ctx.strokeStyle = GOLD; ctx.setLineDash([8, 5]); ctx.beginPath(); ctx.moveTo(a.left, a.y(threshold)); ctx.lineTo(a.right, a.y(threshold)); ctx.stroke();
  }
  return { image: canvas.toDataURL('image/png'), title: scope === 'local' ? 'Local basin · drought history' : 'Upstream catchment · drought history',
    caption: `SPI-12, water years ${first}–${last} (October–September). Brown: drought; teal: wet. Dashed thresholds: −1 drought and −1.5 severe drought. Historical conditions, not a forecast.` };
}

function probabilityFigure(entry, variable) {
  const { canvas, ctx } = surface(145), useful = entry.skill.useful;
  const labels = variable === 'ppt' ? ['Drier', 'Near normal', 'Wetter'] : ['Colder', 'Near normal', 'Warmer'];
  const colors = useful ? (variable === 'ppt' ? ['#bf7b3d', '#d9e4e8', '#26899e'] : ['#4484ac', '#d9e4e8', '#bf7741']) : ['#a7b3b8', '#d5dcdf', '#899da6'];
  let x = 0;
  ['below', 'near', 'above'].forEach((key, i) => {
    const value = entry.forecast.probabilities[key], width = value * W;
    ctx.fillStyle = colors[i]; ctx.fillRect(x, 0, width, 70); x += width;
    ctx.fillStyle = INK; ctx.textAlign = 'left'; ctx.font = '30px Arial';
    ctx.fillText(`${labels[i]} ${Math.round(value * 100)}%`, i * W / 3 + 12, 120);
  });
  return canvas.toDataURL('image/png');
}

// The same diverging ramp as the report page: brown drier (colder), teal wetter (warmer).
const RAMP = ['#8c510a', '#d8b365', '#f1e3bd', '#e8ecea', '#c7eae5', '#5ab4ac', '#01665e'];

function attributionMap(report) {
  const a = report.upstreamInsights?.attribution;
  if (!a) return null;
  const steps = a.extensive ? [-30, -15, -5, 5, 15, 30] : [-1, -0.5, -0.25, 0.25, 0.5, 1];
  const byId = new Map(a.basins.map(b => [b.id, b]));
  const upstreamFill = feature => {
    const basin = byId.get(String(feature.properties.hybas_id));
    const value = a.extensive ? basin?.percent : basin?.anomaly;
    if (value === null || value === undefined || !Number.isFinite(value)) return '#cfd8dccc';
    let i = 0;
    while (i < steps.length && value > steps[i]) i += 1;
    return `${RAMP[i]}dd`;
  };
  const scale = a.extensive ? '−30, −15, −5, +5, +15, +30%' : '−1, −0.5, −0.25, +0.25, +0.5, +1 °C';
  return basinMap(report, { upstreamFill, note: `Each upstream sub-basin’s own departure from its ${a.baseline[0]}–${a.baseline[1]} `
    + `normal in water year ${a.waterYear}: brown ${a.extensive ? 'drier' : 'colder'}, teal ${a.extensive ? 'wetter' : 'warmer'}, `
    + `class breaks at ${scale}. North up; scale at map centre. Shaded relief © Esri.` });
}

function landcoverFigure(report) {
  const cover = report.upstreamInsights?.landcover;
  if (!cover?.coveredShare || !cover.representative) return null;
  const { years, classes, totals } = cover;
  const rows = [0, years.length - 1];
  const height = 90 + rows.length * 70, { canvas, ctx } = surface(height);
  rows.forEach((y, r) => {
    const total = classes.reduce((sum, c) => sum + totals[y][c.code], 0) || 1;
    let x = 110;
    ctx.fillStyle = INK; ctx.textAlign = 'left'; ctx.font = '26px Arial'; ctx.fillText(years[y], 10, 40 + r * 70 + 22);
    for (const c of classes) {
      const width = totals[y][c.code] / total * (W - 130);
      ctx.fillStyle = c.color; ctx.fillRect(x, 40 + r * 70, width, 44); x += width;
    }
  });
  let lx = 110;
  ctx.font = '20px Arial';
  for (const c of classes.filter(c => totals.some(t => t[c.code] > 0))) {
    ctx.fillStyle = c.color; ctx.fillRect(lx, height - 36, 20, 20);
    ctx.fillStyle = INK; ctx.fillText(c.name, lx + 26, height - 19); lx += 36 + ctx.measureText(c.name).width;
  }
  return { image: canvas.toDataURL('image/png'),
    caption: `Land-cover composition of the covered part of the catchment, ${years[0]} and ${years.at(-1)}.` };
}

export async function reportFigures(report) {
  // Fetch the same cached forecast used in the report panel; do not infer it from a screenshot.
  const forecastPromise = report.forecastBasin ? readForecast('/data/atlas/seasonal-forecast/latest.json').catch(() => null) : Promise.resolve(null);
  const map = await basinMap(report);
  const series = ['local', 'upstream'].map(scope => ({ scope,
    figures: [monthlyFigure(report, scope, null), monthlyFigure(report, scope, 36)].filter(Boolean) }));
  const drought = ['local', 'upstream'].map(scope => droughtFigure(report.drought?.[scope], scope)).filter(Boolean);
  const forecast = await forecastPromise;
  const seasonal = forecast ? forecastUnits(forecast, report.forecastBasin).flatMap(unit =>
    forecast.windows.filter(w => ['next3', 'season5'].includes(w.id)).map(window => ({
      title: `${unit.label} · ${window.label}`,
      subtitle: `${forecast.system} · initialized ${forecast.init} · ${forecast.members} members`,
      entries: ['ppt', 'tmean'].flatMap(variable => {
        const entry = forecast.units[unit.key]?.[variable]?.[window.id];
        return entry ? [{ variable, entry, image: probabilityFigure(entry, variable) }] : [];
      }),
    }))) : [];
  const attribution = await attributionMap(report);
  return { map, series, drought, seasonal, attribution, landcover: landcoverFigure(report), forecastMissing: !!report.forecastBasin && !seasonal.length };
}
