// Snow forecast case study: reads page.json and the shared basin outlines, draws every figure.
const PAGE = '/data/case-studies/snow-forecast/region/page.json';
const OUTLINES = '/data/atlas/drought-study/geometry.json';
const NS = 'http://www.w3.org/2000/svg';
const $ = id => document.getElementById(id);
const el = (tag, attrs = {}, parent) => { const node = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v); if (parent) parent.appendChild(node); return node; };
const fmt = (v, d = 2, sign = false) => v == null || !Number.isFinite(v) ? '–' : `${sign && v > 0 ? '+' : ''}${v.toFixed(d)}`.replace('-', '−');
const ISSUES = { 1: '1 Jan', 2: '1 Feb', 3: '1 Mar', 4: '1 Apr' };
// Skill classes: below zero is worse than the average; above, deeper teal is better.
const SKILL = [[-Infinity, '--d2', 'below 0'], [0, '--n0', '0–0.2'], [0.2, '--w1', '0.2–0.4'], [0.4, '--w2', '0.4–0.6'], [0.6, '--w3', '0.6+']];
const skillVar = v => v == null || !Number.isFinite(v) ? 'var(--dr-rule)' : `var(${[...SKILL].reverse().find(([lo]) => v >= lo)[1]})`;
const median = a => { const s = a.filter(Number.isFinite).sort((x, y) => x - y); return s.length ? s[Math.floor((s.length - 1) / 2)] / 2 + s[Math.ceil((s.length - 1) / 2)] / 2 : NaN; };
const quantile = (a, q) => { const s = a.filter(Number.isFinite).sort((x, y) => x - y); const i = (s.length - 1) * q; return s[Math.floor(i)] + (s[Math.ceil(i)] - s[Math.floor(i)]) * (i % 1); };

const tip = $('tip');
const showTip = (event, html) => { tip.innerHTML = html; tip.hidden = false; tip.style.left = Math.min(event.clientX + 14, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = (event.clientY + 14) + 'px'; };
const hideTip = () => { tip.hidden = true; };

function findings(P) {
  const april = P.gauges.map(g => g.skill['4']?.operational);
  const box = $('findings');
  const add = (big, text) => { const d = document.createElement('div'); d.className = 'finding'; d.innerHTML = `<b>${big}</b><span>${text}</span>`; box.appendChild(d); };
  add(`${april.filter(v => v > 0).length} of ${april.length}`, 'gauges where a 1 April forecast beats the previous 30-year average on years it had not seen.');
  add(fmt(median(april)), `median operational skill on 1 April, against ${fmt(median(P.gauges.map(g => g.skill['1']?.operational)))} on 1 January: the forecast needs the winter's snow in place.`);
  const best = [...P.gauges].sort((a, b) => b.skill['4'].operational - a.skill['4'].operational)[0];
  add(fmt(best.skill['4'].operational), `best 1 April skill, at ${best.name} (${best.basin.toLowerCase()} basin).`);
  if (P.pskem) add(fmt(P.pskem.table['4'].operational), 'Pskem at Mullala, 1971–2017, with the operational forecast from 1 April basin snow.');
}

function pskem(P) {
  const t = P.pskem.table;
  $('pskem-table').innerHTML = `<thead><tr><th>Forecast date</th><th style="text-align:left">Chosen predictors</th><th>In-sample adj. R²</th><th>Bootstrap 5–95%</th><th>Cross-validated R²</th><th>Train to 1995, test after (NSE)</th><th>Operational 1971–2017</th><th>Operational 1996–2017</th></tr></thead><tbody>${
    Object.entries(t).map(([k, r]) => `<tr><td>${ISSUES[k]}</td><td style="text-align:left;white-space:normal">${r.predictors.join(', ')}</td><td>${fmt(r.insample)}</td><td>${fmt(r.bootstrap[0])}–${fmt(r.bootstrap[2])}</td><td>${fmt(r.loyo)}</td><td>${fmt(r.split_nse)}</td><td><span class="cell" style="background:${skillVar(r.operational)}">${fmt(r.operational)}</span></td><td><span class="cell" style="background:${skillVar(r.operational_recent)}">${fmt(r.operational_recent)}</span></td></tr>`).join('')}</tbody>`;
  const rows = P.pskem.hindcast;  // [year, observed, raw, corrected, climatology]
  const svg = $('pskem-chart'); const W = 1080, H = 260, pad = { l: 48, r: 14, t: 26, b: 26 };
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('width', W);
  const vals = rows.flatMap(r => [r[1], r[3], r[4]]);
  const lo = Math.floor(Math.min(...vals) / 20) * 20, hi = Math.ceil(Math.max(...vals) / 20) * 20;
  const x = yr => pad.l + (yr - rows[0][0]) / (rows.at(-1)[0] - rows[0][0]) * (W - pad.l - pad.r);
  const y = v => pad.t + (hi - v) / (hi - lo) * (H - pad.t - pad.b);
  for (let v = lo; v <= hi; v += 20) { el('line', { x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v), class: 'grid' }, svg); el('text', { x: pad.l - 6, y: y(v) + 4, 'text-anchor': 'end' }, svg).textContent = v; }
  const line = (i, color, dash) => el('polyline', { points: rows.map(r => `${x(r[0])},${y(r[i])}`).join(' '), fill: 'none', stroke: color, 'stroke-width': 2, 'stroke-dasharray': dash, 'stroke-linejoin': 'round' }, svg);
  line(4, 'var(--dr-muted)', '4 4'); line(3, 'var(--dr-accent)', '0');
  for (const r of rows) el('circle', { cx: x(r[0]), cy: y(r[1]), r: 3.5, fill: 'var(--dr-ink)' }, svg);
  [['Observed', 'var(--dr-ink)', null], ['1 April forecast', 'var(--dr-accent)', '0'], ['Previous 30-year mean', 'var(--dr-muted)', '4 4']].forEach(([n, c, dash], i) => {
    const lx = pad.l + i * 190;
    if (dash == null) el('circle', { cx: lx + 6, cy: 12, r: 3.5, fill: c }, svg); else el('line', { x1: lx, x2: lx + 18, y1: 12, y2: 12, stroke: c, 'stroke-width': 2, 'stroke-dasharray': dash }, svg);
    el('text', { x: lx + 24, y: 16 }, svg).textContent = n;
  });
  for (let yr = Math.ceil(rows[0][0] / 10) * 10; yr <= rows.at(-1)[0]; yr += 10) el('text', { x: x(yr), y: H - 8, 'text-anchor': 'middle' }, svg).textContent = yr;
  for (const r of rows) { const hit = el('rect', { x: x(r[0]) - 8, y: pad.t, width: 16, height: H - pad.t - pad.b, fill: 'transparent' }, svg);
    hit.addEventListener('mousemove', e => showTip(e, `${r[0]}<br>Observed ${r[1].toFixed(0)} m³/s<br>Forecast ${r[3].toFixed(0)} · 30-yr mean ${r[4].toFixed(0)}`)); hit.addEventListener('mouseleave', hideTip); }
  const q = P.pskem.discharge;
  $('pskem-caption').textContent = `April–September mean flow at Pskem–Mullala (m³/s), forecast each year on 1 April from basin snow, using only earlier years. Long-run mean ${q.vegetation_season_mean_m3s.toFixed(0)} m³/s. Models fitted on earlier decades over-predict recent years because flow per unit of snow has fallen; the forecast is shifted by its mean error over the previous ten years.`;
}

function region(P, geometry) {
  const [bx0, by0, bx1, by1] = geometry.bounds; const KX = Math.cos(((by0 + by1) / 2) * Math.PI / 180);
  const svg = $('gauge-map');
  svg.setAttribute('viewBox', `${bx0 * KX} ${-by1} ${(bx1 - bx0) * KX} ${by1 - by0}`); svg.setAttribute('width', '100%'); svg.style.maxWidth = '820px';
  const g = el('g', { transform: `scale(${KX},1)` }, svg);
  for (const d of Object.values(geometry.level07)) el('path', { d, fill: 'var(--dr-surface)', stroke: 'var(--dr-rule)', 'stroke-width': .5, 'vector-effect': 'non-scaling-stroke' }, g);
  for (const d of Object.values(geometry.regions)) el('path', { d, class: 'region' }, g);
  const maxArea = Math.max(...P.gauges.map(x => x.area_km2));
  const dots = P.gauges.map(gauge => {
    const c = el('circle', { cx: gauge.lon, cy: -gauge.lat, r: .08 + .32 * Math.sqrt(gauge.area_km2 / maxArea), stroke: 'var(--dr-ink)', 'stroke-width': 1, 'vector-effect': 'non-scaling-stroke', style: 'cursor:pointer' }, g);
    c.addEventListener('mousemove', e => showTip(e, `${gauge.name}<br>${ISSUES[issue]} skill ${fmt(gauge.skill[issue]?.operational)}`));
    c.addEventListener('mouseleave', hideTip);
    c.addEventListener('click', () => readout(gauge));
    return [gauge, c];
  });
  let issue = '4';
  const paint = () => dots.forEach(([gauge, c]) => c.setAttribute('fill', skillVar(gauge.skill[issue]?.operational)));
  const chips = $('issue-chips');
  for (const k of Object.keys(ISSUES)) { const b = document.createElement('button'); b.type = 'button'; b.textContent = ISSUES[k]; b.setAttribute('aria-pressed', k === issue); b.onclick = () => { issue = k; [...chips.children].forEach(c => c.setAttribute('aria-pressed', c === b)); paint(); }; chips.appendChild(b); }
  paint();
  $('gauge-legend').innerHTML = `<span class="legend-title">Operational skill vs previous 30-year mean</span><div class="legend-row">${SKILL.map(([, v]) => `<i style="background: var(${v})"></i>`).join('')}</div><div class="legend-labels">${SKILL.map(([, , l], i) => `<span style="left:${(i + .5) / SKILL.length * 100}%">${l}</span>`).join('')}</div>`;
  function readout(gauge) {
    $('gauge-readout').innerHTML = `<b>${gauge.name}</b><span class="note">${gauge.river} · ${gauge.basin} · ${gauge.area_km2.toLocaleString()} km² · ${gauge.n_years} seasons ${gauge.veg_years[0]}–${gauge.veg_years[1]}${gauge.regulated_since ? ` · dam since ${gauge.regulated_since}` : ''}</span><dl>${Object.entries(ISSUES).map(([k, n]) => `<dt>${n} operational</dt><dd>${fmt(gauge.skill[k]?.operational)}</dd>`).join('')}<dt>1 Apr cross-validated R²</dt><dd>${fmt(gauge.skill['4']?.loyo)}</dd><dt>1 Apr, 1996–2017</dt><dd>${fmt(gauge.skill['4']?.operational_recent)}</dd><dt>Mean Apr–Sep flow</dt><dd>${gauge.veg_mean_m3s} m³/s</dd></dl>`;
  }
  // Skill by forecast date.
  const s = $('issue-chart'); const W = 760, H = 200, pad = { l: 60, r: 20, t: 16, b: 28 };
  s.setAttribute('viewBox', `0 0 ${W} ${H}`); s.setAttribute('width', W);
  const yv = v => pad.t + (0.8 - v) / 1.2 * (H - pad.t - pad.b);
  for (const v of [-0.4, 0, 0.4, 0.8]) { el('line', { x1: pad.l, x2: W - pad.r, y1: yv(v), y2: yv(v), class: v === 0 ? 'base' : 'grid' }, s); el('text', { x: pad.l - 8, y: yv(v) + 4, 'text-anchor': 'end' }, s).textContent = fmt(v, 1); }
  Object.entries(ISSUES).forEach(([k, n], i) => {
    const v = P.gauges.map(x => x.skill[k]?.operational).filter(Number.isFinite);
    const cx = pad.l + (i + .5) * (W - pad.l - pad.r) / 4;
    el('rect', { x: cx - 26, y: yv(quantile(v, .75)), width: 52, height: yv(quantile(v, .25)) - yv(quantile(v, .75)), rx: 3, fill: skillVar(median(v)), stroke: 'var(--dr-axis)' }, s);
    el('line', { x1: cx - 26, x2: cx + 26, y1: yv(median(v)), y2: yv(median(v)), stroke: 'var(--dr-ink)', 'stroke-width': 2 }, s);
    el('text', { x: cx, y: H - 8, 'text-anchor': 'middle' }, s).textContent = n;
    el('text', { x: cx + 32, y: yv(median(v)) + 4 }, s).textContent = fmt(median(v));
  });
  // Sortable table.
  const cols = [['name', 'Gauge', g => g.name], ['basin', 'Basin', g => g.basin], ['area_km2', 'Area km²', g => g.area_km2], ['n', 'Seasons', g => g.n_years],
    ['s1', '1 Jan', g => g.skill['1']?.operational], ['s3', '1 Mar', g => g.skill['3']?.operational], ['s4', '1 Apr', g => g.skill['4']?.operational],
    ['rec', '1 Apr 1996–', g => g.skill['4']?.operational_recent], ['cv', '1 Apr CV R²', g => g.skill['4']?.loyo], ['reg', 'Dam since', g => g.regulated_since ?? ''], ['gl', 'Glacier share', g => g.glacier_cell_share]];
  let sortKey = 's4', desc = true;
  const table = $('gauge-table');
  const render = () => {
    const get = cols.find(c => c[0] === sortKey)[2];
    const rows = [...P.gauges].sort((a, b) => { const x = get(a), y = get(b); const r = typeof x === 'string' ? String(x).localeCompare(y) : (x ?? -9) - (y ?? -9); return desc ? -r : r; });
    table.innerHTML = `<thead><tr>${cols.map(([k, n]) => `<th><button type="button" data-k="${k}">${n}${k === sortKey ? (desc ? ' ↓' : ' ↑') : ''}</button></th>`).join('')}</tr></thead><tbody>${rows.map(g => `<tr><td>${g.name}</td><td>${g.basin}</td><td>${g.area_km2.toLocaleString()}</td><td>${g.n_years}</td>${['1', '3', '4'].map(k => `<td><span class="cell" style="background:${skillVar(g.skill[k]?.operational)}">${fmt(g.skill[k]?.operational)}</span></td>`).join('')}<td>${fmt(g.skill['4']?.operational_recent)}</td><td>${fmt(g.skill['4']?.loyo)}</td><td>${g.regulated_since ?? ''}</td><td>${(g.glacier_cell_share * 100).toFixed(0)}%</td></tr>`).join('')}</tbody>`;
    table.querySelectorAll('th button').forEach(b => b.onclick = () => { desc = b.dataset.k === sortKey ? !desc : true; sortKey = b.dataset.k; render(); });
  };
  render();
}

function trends(P) {
  const rows = Object.entries(P.single_basin);
  $('trend-table').innerHTML = `<thead><tr><th>Gauge</th><th>Apr–Sep flow since 1951, per decade</th><th>p</th><th>Half-flow date since 1991, days per decade</th><th>p</th><th>1 Apr operational skill</th></tr></thead><tbody>${rows.map(([, s]) => {
    const q = s.trends.vegetation_season_1951, c = s.trends.centre_of_volume_1991;
    const sig = p => p != null && p < .05 ? ' <span class="pill">p < 0.05</span>' : '';
    return `<tr><td>${s.name}</td><td>${fmt(q?.sen_slope_per_decade, 2, true)} m³/s</td><td>${fmt(q?.p_value, 3)}${sig(q?.p_value)}</td><td>${fmt(c?.sen_slope_per_decade, 1, true)}</td><td>${fmt(c?.p_value, 3)}${sig(c?.p_value)}</td><td>${fmt(s.operational_april?.skill_corrected)}</td></tr>`;
  }).join('')}</tbody>`;
}

Promise.all([PAGE, OUTLINES].map(url => fetch(url).then(r => { if (!r.ok) throw Error(`${url} returned ${r.status}`); return r.json(); })))
  .then(([P, geometry]) => {
    $('dr-status').remove();
    $('n-gauges').textContent = P.gauges.length;
    findings(P); if (P.pskem) pskem(P); region(P, geometry); trends(P);
  })
  .catch(error => { $('dr-status').textContent = `The forecast record could not be loaded (${error.message}). Reload the page; if it persists, the study data has not been published yet.`; });
