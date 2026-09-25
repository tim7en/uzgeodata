import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CircleMarker, GeoJSON, Polygon, Polyline, useMap } from 'react-leaflet';
import { Download, PenLine, X } from 'lucide-react';
import {
  AOI_FETCH_CAP, AOI_RULES, aoiFeature, attributesCsv, basinListCsv, dictionaryCsv, exportDocument,
  fetchAll, historyCsv, ringAreaKm2, summarise,
} from './aoiModel.js';
import { formatNumber, systemMeta } from './landingModel.js';

const ACCENT = '#ffd166';

function save(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function readJson(url) {
  const response = await fetch(url);
  if (!response.ok || !(response.headers.get('content-type') || '').includes('json')) {
    throw Error(`${url} is not available (${response.status}).`);
  }
  return response.json();
}

/** Drawing and the selected basins, on the map. Lives inside MapContainer. */
export function AoiLayer({ drawing, vertices, closed, selection, onRectangle, onCancel }) {
  const map = useMap();

  useEffect(() => {
    const container = map.getContainer();
    if (!drawing) return undefined;
    if (window.matchMedia('(max-width: 820px)').matches) container.scrollIntoView({ block: 'center' });
    const wasDragging = map.dragging.enabled();
    const wasDoubleClickZoom = map.doubleClickZoom.enabled();
    const touchAction = container.style.touchAction;
    map.dragging.disable();
    map.doubleClickZoom.disable();
    container.style.touchAction = 'none';
    container.classList.add('land-aoi-drawing');
    let start = null;
    let origin = null;
    const corners = event => {
      const end = map.mouseEventToLatLng(event);
      return [[start.lng, start.lat], [end.lng, start.lat], [end.lng, end.lat], [start.lng, end.lat]];
    };
    const down = event => {
      if (event.button !== 0 || !event.isPrimary) return;
      event.preventDefault();
      event.stopPropagation();
      start = map.mouseEventToLatLng(event);
      origin = [event.clientX, event.clientY];
      container.setPointerCapture(event.pointerId);
    };
    const move = event => {
      if (!start) return;
      event.preventDefault();
      event.stopPropagation();
      onRectangle(corners(event), false);
    };
    const up = event => {
      if (!start) return;
      event.preventDefault();
      event.stopPropagation();
      const valid = Math.abs(event.clientX - origin[0]) >= 5 && Math.abs(event.clientY - origin[1]) >= 5;
      const rectangle = corners(event);
      start = null;
      container.releasePointerCapture(event.pointerId);
      if (valid) onRectangle(rectangle, true);
    };
    const cancel = () => { start = null; onCancel(); };
    container.addEventListener('pointerdown', down, true);
    container.addEventListener('pointermove', move, true);
    container.addEventListener('pointerup', up, true);
    container.addEventListener('pointercancel', cancel);
    const onKey = event => {
      if (event.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      if (wasDragging) map.dragging.enable();
      if (wasDoubleClickZoom) map.doubleClickZoom.enable();
      container.style.touchAction = touchAction;
      container.classList.remove('land-aoi-drawing');
      container.removeEventListener('pointerdown', down, true);
      container.removeEventListener('pointermove', move, true);
      container.removeEventListener('pointerup', up, true);
      container.removeEventListener('pointercancel', cancel);
      window.removeEventListener('keydown', onKey);
    };
  }, [drawing, map, onCancel, onRectangle]);

  const positions = vertices.map(([lng, lat]) => [lat, lng]);
  const outlines = useMemo(() => (selection?.length
    ? { type: 'FeatureCollection', features: selection.map(basin => basin.feature) } : null), [selection]);
  const outlineKey = useMemo(() => (selection || []).map(basin => basin.hybas_id).join(','), [selection]);

  return <>
    {outlines && <GeoJSON key={`aoi-${outlineKey.length}-${outlineKey.slice(0, 64)}`} data={outlines} interactive={false}
      smoothFactor={0} style={{ color: ACCENT, weight: 1.1, opacity: 0.9, fill: false }}/>}
    {closed && positions.length >= 3 && <Polygon positions={positions} interactive={false}
      pathOptions={{ color: ACCENT, weight: 2.2, dashArray: '6 5', fillColor: ACCENT, fillOpacity: 0.06 }}/>}
    {!closed && positions.length >= 2 && <Polyline positions={positions} interactive={false}
      pathOptions={{ color: ACCENT, weight: 2.2, dashArray: '6 5' }}/>}
    {drawing && positions.map((position, index) => <CircleMarker key={index} center={position} radius={4}
      interactive={false} pathOptions={{ color: '#0b1217', weight: 1.5, fillColor: ACCENT, fillOpacity: 1 }}/>)}
  </>;
}

/** The dock section: draw, read the selection, and take it away. */
export function AoiPanel({
  drawing, vertices, closed, rule, selection, loadingGeometry, onStart, onCancel, onClear, onRule, onFit, onUpload, onReport,
}) {
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);
  const panel = useRef(null);
  const cache = useRef({ records: new Map(), histories: new Map() });
  const busy = Boolean(progress);
  const summary = useMemo(() => summarise(selection || []), [selection]);
  const stamp = new Date().toISOString().slice(0, 10);
  const name = suffix => `uzgeodata-aoi-${summary.count}-basins-${stamp}-${suffix}`;

  useEffect(() => { setError(null); }, [selection]);
  useEffect(() => {
    if (closed && window.matchMedia('(max-width: 820px)').matches) panel.current?.scrollIntoView({ block: 'start' });
  }, [closed]);

  // Per-basin documents are fetched once per session; switching from CSV to JSON reuses them.
  const collect = async kind => {
    if (summary.count > AOI_FETCH_CAP) {
      throw Error(`This area holds ${formatNumber(summary.count)} basins. Downloads that read each basin's `
        + `file are limited to ${formatNumber(AOI_FETCH_CAP)}; draw a smaller area or download the basin list.`);
    }
    const store = cache.current[kind];
    const index = await readJson(kind === 'records' ? '/data/atlas/basins/index.json' : '/data/atlas/history/index.json');
    const wanted = selection.map(basin => basin.hybas_id).filter(id => !store.has(id));
    const { results, failures } = await fetchAll(wanted.map(id => `${index.base_url}${id}.json`), {
      onProgress: (done, total) => setProgress({ kind, done, total }),
    });
    results.forEach((document, position) => { if (document) store.set(wanted[position], document); });
    if (failures.length) {
      throw Error(`${failures.length} of ${wanted.length} basin files could not be read, so nothing was `
        + 'downloaded rather than an incomplete table. Check the connection and try again.');
    }
    return selection.map(basin => store.get(basin.hybas_id));
  };

  const run = async task => {
    setError(null);
    setProgress({ kind: 'start', done: 0, total: 0 });
    try { await task(); } catch (cause) { setError(cause.message); } finally { setProgress(null); }
  };

  const downloads = [
    { id: 'list', label: 'Basin list', format: 'CSV', note: 'ids, system, area',
      task: async () => save(name('basins.csv'), basinListCsv(selection), 'text/csv') },
    { id: 'attributes', label: 'Attributes & estimates', format: 'CSV', note: 'HydroATLAS value beside each estimate',
      task: async () => {
        const catalogue = await readJson('/data/atlas/catalogue.json');
        save(name('attributes.csv'), attributesCsv(catalogue, await collect('records')), 'text/csv');
      } },
    { id: 'dictionary', label: 'Column dictionary', format: 'CSV', note: 'labels, units, periods, sources',
      task: async () => save('uzgeodata-attribute-dictionary.csv', dictionaryCsv(await readJson('/data/atlas/catalogue.json')), 'text/csv') },
    { id: 'monthly', label: 'Monthly record', format: 'CSV', note: 'Full published period, one row per month',
      task: async () => save(name('monthly.csv'), historyCsv(await collect('histories')), 'text/csv') },
    { id: 'json', label: 'Everything', format: 'JSON', note: 'area, rule, provenance, all of the above',
      task: async () => {
        const catalogue = await readJson('/data/atlas/catalogue.json');
        const records = await collect('records');
        const histories = await collect('histories');
        const release = await readJson('/release.json').catch(() => null);
        const document = exportDocument({ vertices, rule, basins: selection, catalogue, records, histories,
          release, generatedAt: new Date().toISOString() });
        save(name('all.json'), JSON.stringify(document), 'application/json');
      } },
  ];

  return <div className="land-aoi" ref={panel}>
    <span className="land-aoi-title">Area of interest</span>
    {onUpload && <button type="button" className="land-aoi-primary" onClick={onUpload}>Upload points or polygons · basin reports</button>}
    {!drawing && !closed && <>
      <p className="land-group-note">Select a rectangle to find level-12 basins and download their data.</p>
      <button type="button" className="land-aoi-primary" onClick={onStart}><PenLine size={13}/> Draw area</button>
    </>}
    {drawing && <>
      <p className="land-group-note">Drag across the map to select an area. Release to see its basins; Esc cancels.</p>
      <div className="land-aoi-row">
        <button type="button" onClick={onCancel}>Cancel</button>
      </div>
    </>}
    {closed && <>
      <label className="land-aoi-rule">
        <span>Include basins that</span>
        <select value={rule} onChange={event => onRule(event.target.value)} disabled={busy}>
          {AOI_RULES.map(option => <option key={option.id} value={option.id}>{option.label} — {option.note}</option>)}
        </select>
      </label>
      {loadingGeometry ? <p className="land-group-note">Loading level-12 basins…</p> : <div className="land-aoi-summary">
        <strong>{formatNumber(summary.count)} basins</strong>
        <small>{formatNumber(Math.round(summary.areaKm2))} km² of basin · area drawn {formatNumber(Math.round(ringAreaKm2(vertices)))} km²</small>
        <small>{Object.entries(summary.bySystem).map(([system, count]) => `${systemMeta(system).label} ${formatNumber(count)}`).join(' · ')}</small>
      </div>}
      {onFit && <button type="button" className="land-aoi-primary" disabled={loadingGeometry || !summary.count}
        onClick={onFit}>Zoom to selected polygons</button>}
      {onReport && <button type="button" className="land-aoi-primary" disabled={busy || loadingGeometry || !summary.count}
        onClick={onReport}>Basin report for this area</button>}
      {!loadingGeometry && summary.count > 0 && <ul className="land-aoi-downloads">
        {downloads.map(item => <li key={item.id}>
          <button type="button" disabled={busy} onClick={() => run(item.task)}>
            <Download size={12}/><span><strong>{item.label}</strong><small>{item.note}</small></span><em>{item.format}</em>
          </button>
        </li>)}
      </ul>}
      {progress && progress.total > 0 && <p className="land-group-note" role="status">
        Reading {progress.kind === 'records' ? 'attributes' : 'monthly records'}: {formatNumber(progress.done)} of {formatNumber(progress.total)} basins…</p>}
      {error && <p className="land-aoi-error" role="alert">{error}</p>}
      {!loadingGeometry && summary.count === 0 && <p className="land-group-note">No level-12 basin meets this area under the chosen rule.</p>}
      <p className="land-aoi-caveat">Selection uses the simplified map outlines, so a basin at the very edge can differ from an exact GIS overlay.
        Upstream values must not be summed across basins.</p>
      <div className="land-aoi-row">
        <button type="button" onClick={onStart} disabled={busy}><PenLine size={12}/> Redraw</button>
        <button type="button" onClick={onClear} disabled={busy}><X size={12}/> Clear</button>
      </div>
    </>}
    {/* Downloaded GeoJSON of the area itself is part of the JSON export; offered alone for GIS users. */}
    {closed && vertices.length >= 3 && <button type="button" className="land-aoi-link"
      onClick={() => save(`uzgeodata-aoi-${stamp}.geojson`, JSON.stringify(aoiFeature(vertices)), 'application/geo+json')}>
      Area outline (GeoJSON)</button>}
  </div>;
}
