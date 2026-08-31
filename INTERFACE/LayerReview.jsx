import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { GeoJSON, MapContainer, ScaleControl, TileLayer, ZoomControl, useMap } from 'react-leaflet';
import L from 'leaflet';
import {
  ArrowUpRight, ChevronLeft, ChevronRight, Crosshair, Database, Layers,
  LoaderCircle, Search, Table2,
} from 'lucide-react';

// One layer at a time, drawn on the map with its schema beside it.
//
// The point is inspection rather than analysis: every layer the project holds,
// in a fixed order, with a step control so a reviewer can walk the whole set
// without choosing what to look at next. What matters on screen is whether the
// geometry lands where it should, how many features there are, and whether the
// attribute columns carry anything — so the field table reports a real sample
// value and a fill count rather than a declared type, which is the part that
// tells you a column is empty.

const INDEX_URL = '/data/review-layers.json';

const GROUP_LABELS = {
  ADMIN: 'Administrative boundaries',
  HYDROBASINS: 'Basin watersheds',
  HYDRORIVERS: 'River reaches',
  HYDROLAKES: 'Lakes',
  HAZARDS: 'Hazards',
  PROTECTED: 'Protected areas',
  WATERMGMT: 'Water management',
};

const COLOURS = {
  ADMIN: '#c084fc', HYDROBASINS: '#a78bfa', HYDRORIVERS: '#4cc9f0',
  HYDROLAKES: '#3ddc97', HAZARDS: '#ff5a1f', PROTECTED: '#3ddc97', WATERMGMT: '#f0c74c',
};

const num = value => (value === null || value === undefined ? '—' : Number(value).toLocaleString('en-US'));

const bytes = value => {
  if (!value) return '—';
  const units = ['B', 'KB', 'MB'];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
  return `${size < 10 && unit > 0 ? size.toFixed(1) : Math.round(size)} ${units[unit]}`;
};

function FitBounds({ bbox }) {
  const map = useMap();
  useEffect(() => {
    if (!bbox) return;
    map.fitBounds([[bbox[1], bbox[0]], [bbox[3], bbox[2]]], { padding: [40, 40], animate: false });
  }, [bbox, map]);
  return null;
}

export default function LayerReview() {
  const [index, setIndex] = useState(null);
  const [error, setError] = useState(null);
  const [current, setCurrent] = useState(0);
  const [collection, setCollection] = useState(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [feature, setFeature] = useState(null);
  const request = useRef(0);

  useEffect(() => {
    fetch(INDEX_URL)
      .then(response => (response.ok ? response.json() : Promise.reject(new Error(`${response.status} ${response.statusText}`))))
      .then(setIndex)
      .catch(cause => setError(cause.message));
  }, []);

  const layers = index ? index.layers : [];
  const layer = layers[current];

  // Each layer is fetched as it comes up. They run to tens of megabytes, so only
  // the one being reviewed is ever in memory, and a late response from a layer
  // the reviewer has already stepped past is discarded rather than drawn.
  useEffect(() => {
    if (!layer) return;
    const ticket = ++request.current;
    setLoading(true);
    setCollection(null);
    setFeature(null);
    fetch(layer.url)
      .then(response => (response.ok ? response.json() : Promise.reject(new Error(`${response.status} on ${layer.url}`))))
      .then(data => { if (ticket === request.current) setCollection(data); })
      .catch(cause => { if (ticket === request.current) setError(cause.message); })
      .finally(() => { if (ticket === request.current) setLoading(false); });
  }, [layer]);

  const grouped = useMemo(() => {
    const term = query.trim().toLowerCase();
    const buckets = new Map();
    layers.forEach((entry, position) => {
      if (term && !entry.title.toLowerCase().includes(term)
        && !entry.layer.toLowerCase().includes(term)
        && !entry.group.toLowerCase().includes(term)) return;
      const bucket = buckets.get(entry.group) || [];
      bucket.push({ entry, position });
      buckets.set(entry.group, bucket);
    });
    return [...buckets.entries()];
  }, [layers, query]);

  const step = useCallback(delta => {
    setCurrent(position => Math.min(Math.max(position + delta, 0), layers.length - 1));
  }, [layers.length]);

  useEffect(() => {
    const onKey = event => {
      if (event.target.tagName === 'INPUT') return;
      if (event.key === 'ArrowDown' || event.key === 'j') { event.preventDefault(); step(1); }
      if (event.key === 'ArrowUp' || event.key === 'k') { event.preventDefault(); step(-1); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [step]);

  if (error && !index) return <div className="rv-fatal">
    <h1>Review index unavailable</h1>
    <p>{error}</p>
    <p>Build it with <code>npm run review:build</code>, then reload.</p>
    <a href="/">Return to the portal</a>
  </div>;

  if (!index) return <div className="rv-loading"><LoaderCircle size={16}/> Loading the layer index</div>;

  const colour = COLOURS[layer.group] || '#4cc9f0';
  const punctual = layer.geometryType && layer.geometryType.includes('Point');
  const linear = layer.geometryType && layer.geometryType.includes('LineString');

  return <div className="rv-app">
    <header className="rv-header">
      <a href="/" className="rv-logo" aria-label="UzGeoData home">
        <svg viewBox="0 0 38 38" aria-hidden="true"><path d="M5 7h8v15c0 5 2 8 6 8s6-3 6-8V7h8v16c0 9-5 14-14 14S5 32 5 23V7Z"/><path className="rv-logo-bar" d="M13 2h21v5H13z"/></svg>
        <span>UZ<span>GEO</span>DATA</span>
      </a>
      <div className="rv-header-title">
        <span>LAYER REVIEW</span>
        <strong>{num(layers.length)} layers held</strong>
      </div>
      <nav>
        <a href="/">Portal</a>
        <a href="/hydrography.html">Explorer</a>
        <a href="/catalogue.html">Catalogue</a>
        <a href="/relationships.html">Tables</a>
      </nav>
    </header>

    <main className="rv-main">
      <aside className="rv-list">
        <div className="rv-panel-label"><Layers size={13}/><span>LAYERS</span><small>{num(layers.length)}</small></div>
        <div className="rv-search">
          <Search size={13}/>
          <input value={query} onChange={event => setQuery(event.target.value)}
                 placeholder="Filter layers" aria-label="Filter layers"/>
        </div>
        <div className="rv-scroll">
          {grouped.map(([group, items]) => <div key={group} className="rv-group">
            <div className="rv-group-head">
              <i style={{ background: COLOURS[group] || '#4cc9f0' }}/>
              <strong>{group}</strong>
              <span>{GROUP_LABELS[group] || ''}</span>
              <small>{items.length}</small>
            </div>
            {items.map(({ entry, position }) => <button
              key={entry.id}
              className={position === current ? 'rv-item rv-item-active' : 'rv-item'}
              onClick={() => setCurrent(position)}
            >
              <span className="rv-item-title">{entry.title}</span>
              <span className="rv-item-meta">{num(entry.features)} · {bytes(entry.bytes)}</span>
            </button>)}
          </div>)}
          {!grouped.length && <div className="rv-empty">No layer matches that filter.</div>}
        </div>
      </aside>

      <section className="rv-map-shell">
        <MapContainer center={[41.5, 64.4]} zoom={5} minZoom={3} maxZoom={14} zoomControl={false} preferCanvas>
          <TileLayer
            attribution="&copy; OpenStreetMap contributors &copy; CARTO"
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          />
          <ZoomControl position="bottomleft"/>
          <ScaleControl position="bottomright"/>
          {collection && <GeoJSON
            key={layer.id}
            data={collection}
            style={{ color: colour, weight: linear ? 1 : 0.8, opacity: 0.9,
                     fillColor: colour, fillOpacity: linear ? 0 : 0.18 }}
            pointToLayer={(_feature, latlng) => L.circleMarker(latlng, {
              radius: 3, color: colour, weight: 1, fillColor: colour, fillOpacity: 0.7,
            })}
            onEachFeature={(item, target) => target.on('click', () => setFeature(item.properties))}
          />}
          <FitBounds bbox={layer.bbox}/>
        </MapContainer>

        <div className="rv-map-bar">
          <button onClick={() => step(-1)} disabled={current === 0} title="Previous layer (k)">
            <ChevronLeft size={14}/>
          </button>
          <div className="rv-map-title">
            <span>{layer.group}</span>
            <strong>{layer.title}</strong>
          </div>
          <button onClick={() => step(1)} disabled={current === layers.length - 1} title="Next layer (j)">
            <ChevronRight size={14}/>
          </button>
          <div className="rv-progress"><i style={{ width: `${((current + 1) / layers.length) * 100}%` }}/></div>
          <span className="rv-count">{current + 1} / {layers.length}</span>
        </div>

        {loading && <div className="rv-map-loading"><LoaderCircle size={15}/> Loading {layer.title} · {bytes(layer.bytes)}</div>}
      </section>

      <aside className="rv-detail">
        <div className="rv-panel-label"><Database size={13}/><span>LAYER</span><small>{layer.origin}</small></div>
        <div className="rv-scroll">
          <div className="rv-detail-head">
            <span style={{ color: colour }}>{layer.group}</span>
            <h2>{layer.title}</h2>
            <code>{layer.url}</code>
          </div>

          <div className="rv-facts">
            <div><span>Features</span><strong>{num(layer.features)}</strong></div>
            <div><span>Geometry</span><strong>{layer.geometryType || '—'}</strong></div>
            <div><span>File size</span><strong>{bytes(layer.bytes)}</strong></div>
            <div><span>Attributes</span><strong>{layer.fields.length}</strong></div>
          </div>

          <p className="rv-source">{layer.source}</p>
          {layer.bbox && <p className="rv-bbox">
            Extent {layer.bbox[0]}, {layer.bbox[1]} → {layer.bbox[2]}, {layer.bbox[3]} (EPSG:4326)
            <button onClick={() => setCurrent(current)} className="rv-refit" title="Refit to extent">
              <Crosshair size={11}/> refit
            </button>
          </p>}

          <div className="rv-section-label"><Table2 size={12}/><span>ATTRIBUTES</span><small>{layer.fields.length}</small></div>
          <table className="rv-fields">
            <thead><tr><th>Field</th><th>Sample</th><th>Filled</th></tr></thead>
            <tbody>
              {layer.fields.map(field => {
                const empty = field.filled === 0;
                return <tr key={field.name} className={empty ? 'rv-field-empty' : undefined}>
                  <td><strong>{field.name}</strong><em>{field.type}</em></td>
                  <td className="rv-sample">{field.sample === null || field.sample === undefined
                    ? <span className="rv-none">null</span>
                    : String(field.sample).slice(0, 40)}</td>
                  <td className="rv-mono">
                    {empty ? <span className="rv-none">0</span>
                      : `${Math.round((field.filled / Math.max(layer.features, 1)) * 100)}%`}
                  </td>
                </tr>;
              })}
              {!layer.fields.length && <tr><td colSpan={3} className="rv-none">No attributes.</td></tr>}
            </tbody>
          </table>

          {feature && <>
            <div className="rv-section-label"><Crosshair size={12}/><span>SELECTED FEATURE</span></div>
            <table className="rv-fields">
              <tbody>
                {Object.entries(feature).slice(0, 60).map(([key, value]) => <tr key={key}>
                  <td><strong>{key}</strong></td>
                  <td className="rv-sample" colSpan={2}>{value === null || value === undefined
                    ? <span className="rv-none">null</span> : String(value).slice(0, 60)}</td>
                </tr>)}
              </tbody>
            </table>
          </>}
          {!feature && <p className="rv-hint">Click a feature on the map to read its attributes.</p>}
        </div>
      </aside>
    </main>

    <footer className="rv-footer">
      <span>{index.precision} · {index.crs} · generated {new Date(index.generatedAt).toLocaleString('en-GB')}</span>
      <a href="/catalogue.html">Data catalogue <ArrowUpRight size={13}/></a>
    </footer>
  </div>;
}
