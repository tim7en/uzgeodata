// Drought case study: reads the published study package and draws every figure.
// The figures are written out in drawAll so the page shows a status line until the
// two files arrive, and an actionable message if they do not.
const BASE = '/data/atlas/drought-study/';

async function load() {
  const [summary, geometry] = await Promise.all(['summary.json', 'geometry.json'].map(async name => {
    const response = await fetch(BASE + name, { cache: 'no-cache' });
    if (!response.ok) throw Error(`${name} returned ${response.status}`);
    return response.json();
  }));
  return { ...summary, geometry };
}

function drawAll(D) {
  const $ = id => document.getElementById(id);
  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const NS = 'http://www.w3.org/2000/svg';
  const el = (tag, attrs = {}, parent) => { const node = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v); if (parent) parent.appendChild(node); return node; };
  const fmt = (v, d = 1, sign = true) => v == null || !Number.isFinite(v) ? '–' : (sign && v > 0 ? '+' : '') + v.toFixed(d).replace('-', '−');
  const RAMP = ['--d3', '--d2', '--d1', '--n0', '--w1', '--w2', '--w3'];
  const SCALES = {
    pct: { breaks: [-40, -25, -10, 10, 25, 40], labels: ['−40%', '−25', '−10', '+10', '+25', '+40%'] },
    spi: { breaks: [-2, -1.5, -1, 1, 1.5, 2], labels: ['−2', '−1.5', '−1', '+1', '+1.5', '+2'] },
    pdsi: { breaks: [-4, -3, -2, 2, 3, 4], labels: ['−4', '−3', '−2', '+2', '+3', '+4'] },
  };
  const classOf = (v, scale) => { if (v == null || !Number.isFinite(v)) return null; let i = 0; while (i < scale.breaks.length && v > scale.breaks[i]) i++; if (i < 3 && v === scale.breaks[i]) return i; return i; };
  // Light text on the two strongest classes, whose fill is too dark (light theme) or too bright (dark theme) for ink.
  const cellStyle = (v, scale) => { const c = classOf(v, scale); return `background: ${colorOf(v, scale)}${c === 0 || c === 6 ? '; color: var(--dr-page)' : ''}`; };
  const colorOf = (v, scale) => { const c = classOf(v, scale); return c == null ? 'transparent' : `var(${RAMP[c]})`; };

  const tip = $('tip');
  function showTip(event, html) { tip.innerHTML = html; tip.hidden = false; const x = Math.min(event.clientX + 14, innerWidth - tip.offsetWidth - 8); tip.style.left = x + 'px'; tip.style.top = (event.clientY + 14) + 'px'; }
  function hideTip() { tip.hidden = true; }

  // ---------- data shaping
  const col = (columns) => Object.fromEntries(columns.map((c, i) => [c, i]));
  const S = col(D.series_columns), L = col(D.level07_columns), V = col(D.severity_columns), R = col(D.region_columns);
  const [Y0, Y1] = D.water_years;
  $('span-years').textContent = `${Y0}–${Y1}`;
  const byUnitYear = new Map();
  for (const row of D.level07) byUnitYear.set(row[L.level07] + ':' + row[L.water_year], row);
  const severity = new Map(D.severity.map(row => [row[V.level07], row]));
  const AREAS = [
    ['amu_darya', 'Amu Darya', D.systems.amu_darya], ['syr_darya', 'Syr Darya', D.systems.syr_darya],
    ['amu_darya:headwater', 'Amu headwaters', D.zones['amu_darya:headwater']], ['amu_darya:lowland', 'Amu lowlands', D.zones['amu_darya:lowland']],
    ['syr_darya:headwater', 'Syr headwaters', D.zones['syr_darya:headwater']], ['syr_darya:lowland', 'Syr lowlands', D.zones['syr_darya:lowland']],
  ].filter(a => a[2]);
  const unitLabel = id => { const u = D.units[id] || {}; const sys = u.system === 'amu_darya' ? 'Amu' : 'Syr'; return `${sys} ${u.headwater ? 'headwaters' : 'lowlands'} · ${u.lon?.toFixed(1)}°E ${u.lat?.toFixed(1)}°N${u.region ? ' · ' + u.region : ''}`; };

  // ---------- headline findings, computed from the data
  (function findings() {
    const box = $('findings');
    const add = (big, text) => { const d = document.createElement('div'); d.className = 'finding'; d.innerHTML = `<b>${big}</b><span>${text}</span>`; box.appendChild(d); };
    for (const [key, name, rows] of AREAS.slice(0, 2)) {
      const recent = rows.filter(r => r[S.water_year] >= 1991);
      const worst = recent.reduce((a, b) => (b[S.spi12] < a[S.spi12] ? b : a));
      add(`${worst[S.water_year]}`, `Driest ${name} water year since 1991: SPI ${fmt(worst[S.spi12], 2)}, precipitation ${fmt(worst[S.ppt_anom_pct_wmo], 0)}% against 1991–2020.`);
    }
    const ranked = [...D.severity].sort((a, b) => b[V.severe_years] - a[V.severe_years]);
    const counts = D.severity.map(r => r[V.severe_years]);
    const many = counts.filter(c => c >= 4).length;
    add(`${many} of ${counts.length}`, `sub-basins had four or more severe drought years from 1991 to 2025. The most exposed is ${unitLabel(ranked[0][V.level07])} (${ranked[0][V.severe_years]} years).`);
    const drier = D.severity.filter(r => r[V.norm_shift_pct] < -5).length, wetter = D.severity.filter(r => r[V.norm_shift_pct] > 5).length;
    add(`${drier} drier · ${wetter} wetter`, `sub-basins whose 1991–2020 normal moved more than 5% from the 1961–1990 normal.`);
  })();

  // ---------- section 1: timelines
  let area = AREAS[0][0];
  function drawTimeline() {
    const rows = AREAS.find(a => a[0] === area)[2];
    const W = 1080, H = 230, P = { l: 44, r: 12, t: 16, b: 26 };
    const n = Y1 - Y0 + 1, bw = (W - P.l - P.r) / n;
    const x = y => P.l + (y - Y0) * bw;
    // SPI bars
    const svg = $('spi-chart'); svg.innerHTML = ''; svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('width', W);
    const lim = 3, yv = v => P.t + (lim - Math.max(-lim, Math.min(lim, v))) / (2 * lim) * (H - P.t - P.b);
    for (const t of [-2, -1, 0, 1, 2]) { el('line', { x1: P.l, x2: W - P.r, y1: yv(t), y2: yv(t), class: t === 0 ? 'base' : 'grid' }, svg); el('text', { x: P.l - 6, y: yv(t) + 4, 'text-anchor': 'end' }, svg).textContent = fmt(t, 0); }
    for (const ev of D.documented.filter(e => (area.startsWith('amu') ? e.system_id === 'amu_darya' : e.system_id === 'syr_darya'))) {
      const cx = x(ev.water_year) + bw / 2;
      el('line', { x1: cx, x2: cx, y1: P.t - 6, y2: H - P.b, stroke: ev.kind === 'dry' ? 'var(--event-dry)' : 'var(--event-wet)', 'stroke-dasharray': '2 3', 'stroke-width': 1 }, svg);
      el('text', { x: cx, y: P.t - 6 + 4, 'text-anchor': 'middle', style: `fill: ${ev.kind === 'dry' ? 'var(--event-dry)' : 'var(--event-wet)'}; font-size: 10px` }, svg).textContent = '▼';
    }
    for (const r of rows) {
      const v = r[S.spi12]; if (v == null) continue;
      const y0 = yv(0), y = yv(v), h = Math.max(1, Math.abs(y - y0));
      const bar = el('rect', { x: x(r[S.water_year]) + 1, y: Math.min(y, y0), width: Math.max(1, bw - 2), height: h, rx: 1.5, fill: colorOf(v, SCALES.spi) }, svg);
      const hit = el('rect', { x: x(r[S.water_year]), y: P.t, width: bw, height: H - P.t - P.b, fill: 'transparent' }, svg);
      hit.addEventListener('mousemove', e => showTip(e, `WY ${r[S.water_year]}<br>SPI-12 ${fmt(v, 2)}<br>P ${r[S.ppt].toFixed(0)} mm (${fmt(r[S.ppt_anom_pct_wmo], 0)}% vs 1991–2020)<br>PDSI ${fmt(r[S.pdsi], 2)}`));
      hit.addEventListener('mouseleave', hideTip);
    }
    for (let y = Y0 + (10 - Y0 % 10) % 10; y <= Y1; y += 10) el('text', { x: x(y) + bw / 2, y: H - 8, 'text-anchor': 'middle' }, svg).textContent = y;
    el('text', { x: P.l, y: 11 }, svg).textContent = 'SPI-12';

    // Precipitation with norms (single axis, mm)
    const s2 = $('ppt-chart'); s2.innerHTML = ''; const H2 = 250; s2.setAttribute('viewBox', `0 0 ${W} ${H2}`); s2.setAttribute('width', W);
    const vals = rows.flatMap(r => [r[S.ppt], r[S.ppt_trailing_10], r[S.ppt_trailing_30]]).filter(Number.isFinite);
    const top = Math.ceil(Math.max(...vals) / 100) * 100;
    const yp = v => P.t + (1 - v / top) * (H2 - P.t - P.b);
    for (let t = 0; t <= top; t += top / 4) { el('line', { x1: P.l, x2: W - P.r, y1: yp(t), y2: yp(t), class: t === 0 ? 'base' : 'grid' }, s2); el('text', { x: P.l - 6, y: yp(t) + 4, 'text-anchor': 'end' }, s2).textContent = Math.round(t); }
    for (const r of rows) el('rect', { x: x(r[S.water_year]) + 1, y: yp(r[S.ppt]), width: Math.max(1, bw - 2), height: yp(0) - yp(r[S.ppt]), rx: 1.5, fill: 'var(--dr-axis)', opacity: .8 }, s2);
    const lines = [['ppt_wmo', 'var(--dr-ink)', '0', '1991–2020 normal'], ['ppt_trailing_10', 'var(--d2)', '0', 'Trailing 10 yr'], ['ppt_trailing_20', 'var(--w2)', '0', 'Trailing 20 yr'], ['ppt_trailing_30', 'var(--dr-accent)', '5 3', 'Trailing 30 yr']];
    lines.forEach(([key, color, dash, name], i) => {
      const pts = rows.filter(r => Number.isFinite(r[S[key]])).map(r => `${x(r[S.water_year]) + bw / 2},${yp(r[S[key]])}`).join(' ');
      el('polyline', { points: pts, fill: 'none', stroke: color, 'stroke-width': 2, 'stroke-dasharray': dash, 'stroke-linejoin': 'round' }, s2);
      const lx = P.l + 8 + i * 150; el('line', { x1: lx, x2: lx + 18, y1: 10, y2: 10, stroke: color, 'stroke-width': 2, 'stroke-dasharray': dash }, s2); el('text', { x: lx + 24, y: 14 }, s2).textContent = name;
    });
    for (const r of rows) { const hit = el('rect', { x: x(r[S.water_year]), y: P.t, width: bw, height: H2 - P.t - P.b, fill: 'transparent' }, s2);
      hit.addEventListener('mousemove', e => showTip(e, `WY ${r[S.water_year]} · ${r[S.ppt].toFixed(0)} mm<br>1991–2020: ${r[S.ppt_wmo].toFixed(0)} mm<br>10 yr: ${Number.isFinite(r[S.ppt_trailing_10]) ? r[S.ppt_trailing_10].toFixed(0) : '–'} · 20 yr: ${Number.isFinite(r[S.ppt_trailing_20]) ? r[S.ppt_trailing_20].toFixed(0) : '–'} · 30 yr: ${Number.isFinite(r[S.ppt_trailing_30]) ? r[S.ppt_trailing_30].toFixed(0) : '–'} mm`));
      hit.addEventListener('mouseleave', hideTip); }
    for (let y = Y0 + (10 - Y0 % 10) % 10; y <= Y1; y += 10) el('text', { x: x(y) + bw / 2, y: H2 - 8, 'text-anchor': 'middle' }, s2).textContent = y;
    const last = rows[rows.length - 1];
    $('timeline-caption').textContent = `Precipitation in mm per water year, area-weighted over ${AREAS.find(a => a[0] === area)[1]}. ▼ marks documented dry (brown) and wet (teal) years. WY ${last[S.water_year]}: ${last[S.ppt].toFixed(0)} mm against a 1991–2020 normal of ${last[S.ppt_wmo].toFixed(0)} mm and a trailing 10-year mean of ${last[S.ppt_trailing_10].toFixed(0)} mm.`;
  }
  const chips = $('system-chips');
  for (const [key, name] of AREAS) { const b = document.createElement('button'); b.type = 'button'; b.textContent = name; b.setAttribute('aria-pressed', key === area); b.onclick = () => { area = key; [...chips.children].forEach(c => c.setAttribute('aria-pressed', c === b)); drawTimeline(); }; chips.appendChild(b); }

  // ---------- maps
  const [bx0, by0, bx1, by1] = D.geometry.bounds;
  const KX = Math.cos(((by0 + by1) / 2) * Math.PI / 180);
  function baseMap(svg, width) {
    svg.innerHTML = '';
    const w = (bx1 - bx0) * KX, h = by1 - by0;
    svg.setAttribute('viewBox', `${bx0 * KX} ${-by1} ${w} ${h}`);
    svg.setAttribute('width', '100%'); svg.style.maxWidth = width + 'px'; svg.style.height = 'auto';
    const g = el('g', { transform: `scale(${KX},1)` }, svg);
    const units = {};
    for (const [id, d] of Object.entries(D.geometry.level07)) units[id] = el('path', { d, class: 'unit', 'data-id': id }, g);
    const rg = el('g', {}, g);
    for (const d of Object.values(D.geometry.regions)) el('path', { d, class: 'region' }, rg);
    return units;
  }
  function legend(box, scale, title) {
    box.innerHTML = `<span class="legend-title">${title}</span><div class="legend-row">${RAMP.map(v => `<i style="background: var(${v})"></i>`).join('')}</div><div class="legend-labels">${scale.labels.map((l, i) => `<span style="left: ${(i + 1) / RAMP.length * 100}%">${l}</span>`).join('')}</div>`;
  }
  const METRICS = [
    ['ppt_anom_pct_wmo', 'Precipitation vs 1991–2020 normal (%)', 'pct', 'WMO 1991–2020 standard normal'],
    ['ppt_anom_pct_trailing_10', 'Precipitation vs previous 10 years (%)', 'pct', 'mean of the 10 water years before'],
    ['ppt_anom_pct_trailing_20', 'Precipitation vs previous 20 years (%)', 'pct', 'mean of the 20 water years before'],
    ['ppt_anom_pct_trailing_30', 'Precipitation vs previous 30 years (%)', 'pct', 'mean of the 30 water years before'],
    ['ppt_anom_pct_early', 'Precipitation vs 1961–1990 normal (%)', 'pct', 'previous WMO normal'],
    ['spi12', 'SPI-12 (water year)', 'spi', 'standardised against 1991–2020'],
    ['pdsi', 'PDSI, water-year mean', 'pdsi', 'Palmer index; below −2 is moderate drought'],
    ['pdsi_diff_wmo', 'PDSI vs its 1991–2020 mean', 'pdsi', 'difference in index units'],
    ['pdsi_diff_trailing_10', 'PDSI vs previous 10 years', 'pdsi', 'difference in index units'],
  ];
  const metricSel = $('metric');
  for (const [key, name] of METRICS) metricSel.add(new Option(name, key));
  const yearInput = $('year'); yearInput.min = Y0; yearInput.max = Y1; yearInput.value = 2021;
  let selected = null;
  const mainUnits = baseMap($('map'), 820);
  function paintMain() {
    const [key, name, scaleKey, meaning] = METRICS.find(m => m[0] === metricSel.value);
    const scale = SCALES[scaleKey], year = +yearInput.value;
    $('year-out').textContent = year;
    let dry = 0, total = 0;
    for (const [id, path] of Object.entries(mainUnits)) {
      const row = byUnitYear.get(id + ':' + year); const v = row ? row[L[key]] : null;
      path.setAttribute('fill', v == null ? 'var(--dr-rule)' : colorOf(v, scale));
      if (v != null) { total++; if (classOf(v, scale) <= 2) dry++; }
    }
    legend($('legend'), scale, name);
    $('map-note').textContent = total ? `${dry} of ${total} sub-basins fall in the three dry classes in WY ${year}. Norm: ${meaning}.` : `No values: the ${meaning} needs earlier years than WY ${year}.`;
    readout();
  }
  function readout() {
    const box = $('readout'); if (!selected) return;
    const year = +yearInput.value, row = byUnitYear.get(selected + ':' + year), sev = severity.get(selected);
    if (!row) { box.innerHTML = '<span class="note">No data for this unit and year.</span>'; return; }
    const u = D.units[selected];
    box.innerHTML = `<b>${unitLabel(selected)}</b><span class="note">Unit ${selected} · ${Math.round(u.area_km2).toLocaleString()} km² · WY ${year}</span>
    <dl><dt>Precipitation</dt><dd>${row[L.ppt].toFixed(0)} mm</dd>
    <dt>vs 1991–2020</dt><dd>${fmt(row[L.ppt_anom_pct_wmo], 0)}%</dd>
    <dt>vs prev. 10 yr</dt><dd>${fmt(row[L.ppt_anom_pct_trailing_10], 0)}%</dd>
    <dt>vs prev. 20 yr</dt><dd>${fmt(row[L.ppt_anom_pct_trailing_20], 0)}%</dd>
    <dt>vs prev. 30 yr</dt><dd>${fmt(row[L.ppt_anom_pct_trailing_30], 0)}%</dd>
    <dt>SPI-12</dt><dd>${fmt(row[L.spi12], 2)}</dd>
    <dt>PDSI</dt><dd>${fmt(row[L.pdsi], 2)}</dd>
    <dt>Severe years 1991–2025</dt><dd>${sev ? sev[V.severe_years] : '–'}</dd></dl>`;
  }
  for (const [id, path] of Object.entries(mainUnits)) {
    path.addEventListener('click', () => { if (selected) mainUnits[selected].classList.remove('sel'); selected = id; path.classList.add('sel'); readout(); });
    path.addEventListener('mousemove', e => { const row = byUnitYear.get(id + ':' + yearInput.value); const m = METRICS.find(m => m[0] === metricSel.value); showTip(e, `${unitLabel(id)}<br>${m[1]}: ${row ? fmt(row[L[m[0]]], m[2] === 'pct' ? 0 : 2) : '–'}`); });
    path.addEventListener('mouseleave', hideTip);
  }
  metricSel.onchange = paintMain; yearInput.oninput = paintMain;
  const jumps = $('year-jumps');
  for (const y of [...new Set(D.documented.map(e => e.water_year))].sort()) {
    const kind = D.documented.find(e => e.water_year === y).kind;
    const b = document.createElement('button'); b.type = 'button'; b.textContent = `${y} ${kind}`; b.onclick = () => { yearInput.value = y; paintMain(); }; jumps.appendChild(b);
  }

  // severity and shift maps
  const sevUnits = baseMap($('map-severe'), 560), shiftUnits = baseMap($('map-shift'), 560);
  const sevVar = v => v === 0 ? '--n0' : v <= 2 ? '--d1' : v <= 5 ? '--d2' : '--d3';
  for (const [id, path] of Object.entries(sevUnits)) {
    const r = severity.get(id); const v = r ? r[V.severe_years] : null;
    path.setAttribute('fill', v == null ? 'var(--dr-rule)' : `var(${sevVar(v)})`);
    path.addEventListener('mousemove', e => showTip(e, `${unitLabel(id)}<br>Severe years: ${v ?? '–'} · worst WY ${r ? r[V.worst_year] : '–'} (SPI ${r ? fmt(r[V.worst_spi], 2) : '–'})`));
    path.addEventListener('mouseleave', hideTip);
  }
  $('legend-severe').innerHTML = `<span class="legend-title">Water years with SPI-12 ≤ −1.5, 1991–2025</span><div class="legend-row">${['--n0', '--d1', '--d2', '--d3'].map(v => `<i style="background: var(${v})"></i>`).join('')}</div><div class="legend-labels">${['0', '1–2', '3–5', '6+'].map((l, i) => `<span style="left: ${(i + .5) / 4 * 100}%">${l}</span>`).join('')}</div>`;
  const shiftScale = { breaks: [-15, -10, -5, 5, 10, 15], labels: ['−15%', '−10', '−5', '+5', '+10', '+15%'] };
  for (const [id, path] of Object.entries(shiftUnits)) {
    const r = severity.get(id); const v = r ? r[V.norm_shift_pct] : null;
    path.setAttribute('fill', v == null ? 'var(--dr-rule)' : colorOf(v, shiftScale));
    path.addEventListener('mousemove', e => showTip(e, `${unitLabel(id)}<br>1961–1990: ${r ? r[V.ppt_early].toFixed(0) : '–'} mm · 1991–2020: ${r ? r[V.ppt_wmo].toFixed(0) : '–'} mm<br>Change ${r ? fmt(v, 1) : '–'}%`));
    path.addEventListener('mouseleave', hideTip);
  }
  legend($('legend-shift'), shiftScale, 'Change in water-year precipitation normal, 1991–2020 vs 1961–1990');

  // ranking table
  (function rank() {
    const rows = [...D.severity].sort((a, b) => b[V.severe_years] - a[V.severe_years] || a[V.worst_spi] - b[V.worst_spi]).slice(0, 12);
    $('rank-table').innerHTML = `<thead><tr><th>Sub-basin</th><th>Severe yrs</th><th>Moderate+ yrs</th><th>Wet yrs</th><th>Worst WY</th><th>Worst SPI</th><th>Normal mm</th><th>Normal shift</th></tr></thead><tbody>${rows.map(r => `<tr><td>${unitLabel(r[V.level07])}</td><td>${r[V.severe_years]}</td><td>${r[V.moderate_years]}</td><td>${r[V.wet_years]}</td><td>${r[V.worst_year]}</td><td><span class="cell" style="${cellStyle(r[V.worst_spi], SCALES.spi)}">${fmt(r[V.worst_spi], 2)}</span></td><td>${r[V.ppt_wmo].toFixed(0)}</td><td>${fmt(r[V.norm_shift_pct], 1)}%</td></tr>`).join('')}</tbody>`;
  })();

  // ---------- section 4: documented events
  (function events() {
    const sys = { amu_darya: 'Amu', syr_darya: 'Syr' };
    const grouped = {}; for (const e of D.documented) (grouped[e.water_year] ||= []).push(e);
    const verdict = (e) => {
      if (e.kind === 'dry') return e.spi12 <= -1 ? `Confirmed: ${e.spi12 <= -1.5 ? 'severe' : 'moderate'} drought, driest ${e.dry_rank} of ${e.years}.` : e.pdsi <= -2 ? `Precipitation near normal, but PDSI ${fmt(e.pdsi, 1)} shows a drought state.` : `Not a precipitation drought in this system (rank ${e.dry_rank}).`;
      const wetRank = e.years - e.dry_rank + 1;
      return e.spi12 >= 1 ? `Confirmed: wet year, ${wetRank} wettest of ${e.years}.` : `Not unusually wet in precipitation (wettest rank ${wetRank}). The event may reflect snowpack or melt timing.`;
    };
    $('event-table').innerHTML = `<thead><tr><th>Water year</th><th>Record</th><th>System</th><th>SPI-12</th><th>P vs 1991–2020</th><th>PDSI</th><th>Runoff vs normal</th><th style="text-align:left">In this data</th></tr></thead><tbody>${
      Object.entries(grouped).sort((a, b) => a[0] - b[0]).flatMap(([y, list]) => list.map((e, i) => `<tr>${i === 0 ? `<td rowspan="${list.length}">${y}</td><td rowspan="${list.length}"><span class="tag ${e.kind}">${e.kind}</span><br><a href="${e.url}" target="_blank" rel="noopener" style="font-size:.75rem;white-space:normal">${e.source}</a></td>` : ''}<td>${sys[e.system_id]}</td><td><span class="cell" style="${cellStyle(e.spi12, SCALES.spi)}">${fmt(e.spi12, 2)}</span></td><td>${fmt(e.ppt_anom_pct_wmo, 0)}%</td><td>${fmt(e.pdsi, 2)}</td><td>${fmt(e.q_anom_pct_wmo, 0)}%</td><td class="verdict">${verdict(e)}</td></tr>`)).join('')}</tbody>`;
  })();

  // ---------- section 5: downstream
  const regionRows = D.regions;
  const downSel = $('down-year');
  for (let y = Y1; y >= Y0; y--) downSel.add(new Option(y, y));
  downSel.value = 2021;
  function drawDown() {
    const year = +downSel.value;
    const rows = regionRows.filter(r => r[R.water_year] === year).sort((a, b) => a[R.system_id].localeCompare(b[R.system_id]) || (a[R.up_q_anom_pct_wmo] - b[R.up_q_anom_pct_wmo]));
    const svg = $('down-chart'); svg.innerHTML = '';
    const W = 1080, rowH = 26, P = { l: 230, r: 20, t: 34, b: 28 }, H = P.t + rows.length * rowH + P.b;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('width', W);
    const vals = rows.flatMap(r => [r[R.ppt_anom_pct_wmo], r[R.up_q_anom_pct_wmo]]).filter(Number.isFinite);
    const lim = Math.max(40, Math.ceil(Math.max(...vals.map(Math.abs)) / 20) * 20);
    const xv = v => P.l + (v + lim) / (2 * lim) * (W - P.l - P.r);
    for (let t = -lim; t <= lim; t += lim / 2) { el('line', { x1: xv(t), x2: xv(t), y1: P.t - 6, y2: H - P.b, class: t === 0 ? 'base' : 'grid' }, svg); el('text', { x: xv(t), y: H - 10, 'text-anchor': 'middle' }, svg).textContent = fmt(t, 0) + '%'; }
    const key = [['Local precipitation', 'var(--dr-muted)', 'circle'], ['Upstream runoff generation', 'var(--dr-ink)', 'rect']];
    key.forEach(([n, c, shape], i) => { const lx = P.l + i * 230; if (shape === 'circle') el('circle', { cx: lx + 6, cy: 14, r: 5, fill: 'var(--dr-surface)', stroke: c, 'stroke-width': 2 }, svg); else el('rect', { x: lx + 1, y: 9, width: 10, height: 10, fill: c }, svg); el('text', { x: lx + 18, y: 18 }, svg).textContent = n; });
    rows.forEach((r, i) => {
      const y = P.t + i * rowH + rowH / 2;
      el('text', { x: P.l - 10, y: y + 4, 'text-anchor': 'end', style: 'fill: var(--dr-ink-2); font-family: var(--dr-body); font-size: 12px' }, svg).textContent = `${r[R.ADM1_EN].replace('Republic of ', '')} (${r[R.system_id] === 'amu_darya' ? 'Amu' : 'Syr'})`;
      const a = r[R.ppt_anom_pct_wmo], b = r[R.up_q_anom_pct_wmo];
      if (Number.isFinite(a) && Number.isFinite(b)) el('line', { x1: xv(a), x2: xv(b), y1: y, y2: y, stroke: 'var(--dr-axis)', 'stroke-width': 2 }, svg);
      if (Number.isFinite(b)) el('rect', { x: xv(b) - 5, y: y - 5, width: 10, height: 10, fill: colorOf(b, SCALES.pct), stroke: 'var(--dr-ink)', 'stroke-width': 1.5 }, svg);
      if (Number.isFinite(a)) el('circle', { cx: xv(a), cy: y, r: 5, fill: colorOf(a, SCALES.pct), stroke: 'var(--dr-muted)', 'stroke-width': 2 }, svg);
      const hit = el('rect', { x: 0, y: y - rowH / 2, width: W, height: rowH, fill: 'transparent' }, svg);
      hit.addEventListener('mousemove', e => showTip(e, `${r[R.ADM1_EN]} · WY ${year}<br>Local P ${fmt(a, 0)}% · SPI ${fmt(r[R.spi12], 2)}<br>Upstream runoff ${fmt(b, 0)}% · upstream SPI ${fmt(r[R.up_spi12], 2)}`));
      hit.addEventListener('mouseleave', hideTip);
    });
    $('down-table').innerHTML = `<thead><tr><th>Region</th><th>Local P mm</th><th>Local vs normal</th><th>Local SPI</th><th>Upstream area km²</th><th>Upstream runoff vs normal</th><th>Upstream SPI</th><th>Upstream runoff km³</th></tr></thead><tbody>${rows.map(r => `<tr><td>${r[R.ADM1_EN]}</td><td>${r[R.ppt].toFixed(0)}</td><td><span class="cell" style="${cellStyle(r[R.ppt_anom_pct_wmo], SCALES.pct)}">${fmt(r[R.ppt_anom_pct_wmo], 0)}%</span></td><td>${fmt(r[R.spi12], 2)}</td><td>${Math.round(D.reaches[r[R.ADM1_PCODE]].up_area_km2).toLocaleString()}</td><td><span class="cell" style="${cellStyle(r[R.up_q_anom_pct_wmo], SCALES.pct)}">${fmt(r[R.up_q_anom_pct_wmo], 0)}%</span></td><td>${fmt(r[R.up_spi12], 2)}</td><td>${r[R.up_q_mcm] == null ? '–' : (r[R.up_q_mcm] / 1000).toFixed(1)}</td></tr>`).join('')}</tbody>`;
  }
  downSel.onchange = drawDown;

  $('caveats').innerHTML = D.caveats.map(c => `<li>${c}</li>`).join('');
  drawTimeline(); paintMain(); drawDown();
}

load().then(D => { document.getElementById('dr-status').remove(); drawAll(D); })
  .catch(error => { document.getElementById('dr-status').textContent = `The drought record could not be loaded (${error.message}). Reload the page; if it persists, the study data has not been published yet.`; });
