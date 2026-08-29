import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { GeoJSON, MapContainer, ScaleControl, TileLayer, ZoomControl, useMap } from 'react-leaflet';
import L from 'leaflet';
import {
  ArrowUpRight, ChevronRight, Database, Droplets, Layers, LoaderCircle,
  MapPin, Network, Search, Share2, Waves,
} from 'lucide-react';

const INDEX_URL = '/data/hydrography/relationships.json';
const LIST_LIMIT = 220;
const DRAW_LIMIT = 6000;
const SELECTED_COLOR = '#ff5a1f';

function num(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return Number(value).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

const TYPES = {
  rivers: {
    label: 'Rivers', singular: 'reach', plural: 'reaches', icon: Waves, color: '#4cc9f0',
    idField: 'HYRIV_ID', rank: r => r.upstreamKm2 ?? 0,
    filter: { key: 'strahlerOrder', label: 'Min Strahler order', min: 1, max: 8, step: 1, initial: 4, format: v => `≥ ${v}` },
    name: r => `Reach ${r.id}`,
    detail: r => `Order ${r.strahlerOrder} · ${num(r.lengthKm, 2)} km`,
  },
  lakes: {
    label: 'Lakes', singular: 'lake', plural: 'lakes', icon: Droplets, color: '#3ddc97',
    idField: 'Hylak_id', rank: r => r.areaKm2 ?? 0,
    filter: { key: 'areaKm2', label: 'Min surface area', min: 0, max: 50, step: 1, initial: 0, format: v => `≥ ${v} km²` },
    name: r => r.name || `Lake ${r.id}`,
    detail: r => `${num(r.areaKm2, 2)} km² · ${r.elevationM ?? '—'} m`,
  },
  basins: {
    label: 'Basins', singular: 'basin', plural: 'basins', icon: Layers, color: '#a78bfa',
    idField: 'HYBAS_ID', rank: r => r.uzbekistanKm2 ?? 0,
    filter: { key: 'uzbekistanKm2', label: 'Min area in Uzbekistan', min: 0, max: 1000, step: 25, initial: 0, format: v => `≥ ${v} km²` },
    name: r => `Basin ${r.pfafId}`,
    detail: r => `${num(r.uzbekistanKm2, 1)} km² · ${num(r.uzbekistanPercent, 0)}% in UZ`,
  },
};

function Logo() {
  return <a href="/" className="hydro-logo" aria-label="UzGeoData home">
    <svg viewBox="0 0 38 38" aria-hidden="true"><path d="M5 7h8v15c0 5 2 8 6 8s6-3 6-8V7h8v16c0 9-5 14-14 14S5 32 5 23V7Z"/><path className="hydro-logo-bar" d="M13 2h21v5H13z"/></svg>
    <span>UZ<span>GEO</span>DATA</span>
  </a>;
}

function MapFocus({ bounds }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) map.flyToBounds(bounds, { padding: [56, 56], maxZoom: 11, duration: 0.6 });
  }, [bounds, map]);
  return null;
}

export default function HydrographyExplorer() {
  const [index, setIndex] = useState(null);
  const [error, setError] = useState(null);
  const [type, setType] = useState('rivers');
  const [query, setQuery] = useState('');
  const [thresholds, setThresholds] = useState(
    () => Object.fromEntries(Object.entries(TYPES).map(([key, config]) => [key, config.filter.initial])),
  );
  const [selected, setSelected] = useState(null);
  const [geo, setGeo] = useState({});
  const [loadingGeo, setLoadingGeo] = useState(true);
  const [focus, setFocus] = useState(null);
  const requested = useRef(new Set());

  useEffect(() => {
    let live = true;
    fetch(INDEX_URL)
      .then(response => (response.ok ? response.json() : Promise.reject(new Error(`${response.status} ${response.statusText}`))))
      .then(data => { if (live) setIndex(data); })
      .catch(cause => { if (live) setError(cause.message); });
    return () => { live = false; };
  }, []);

  const loadLayer = useCallback((key, url) => {
    if (!url || requested.current.has(key)) return;
    requested.current.add(key);
    setLoadingGeo(true);
    fetch(url)
      .then(response => (response.ok ? response.json() : Promise.reject(new Error(`${response.status} on ${key}`))))
      .then(collection => setGeo(current => ({ ...current, [key]: collection })))
      .catch(cause => setError(cause.message))
      .finally(() => setLoadingGeo(false));
  }, []);

  useEffect(() => {
    if (!index) return;
    loadLayer('boundary', index.layers.boundary);
    loadLayer(type, index.layers[type]);
  }, [index, type, loadLayer]);

  const records = useMemo(() => {
    if (!index) return {};
    return Object.fromEntries(Object.keys(TYPES).map(key => [key, new Map(index[key].map(r => [r.id, r]))]));
  }, [index]);

  const graph = useMemo(() => {
    if (!index) return null;
    const upstream = new Map();
    const basinRivers = new Map();
    const basinLakes = new Map();
    const basinChildren = new Map();
    const push = (map, key, value) => {
      if (!key) return;
      const bucket = map.get(key);
      if (bucket) bucket.push(value); else map.set(key, [value]);
    };
    index.rivers.forEach(river => {
      push(upstream, river.nextDown, river.id);
      push(basinRivers, river.basinId, river.id);
    });
    index.lakes.forEach(lake => push(basinLakes, lake.basinId, lake.id));
    index.basins.forEach(basin => push(basinChildren, basin.nextDown, basin.id));
    return { upstream, basinRivers, basinLakes, basinChildren };
  }, [index]);

  const config = TYPES[type];
  const threshold = thresholds[type];

  const matches = useMemo(() => {
    if (!index) return [];
    const term = query.trim().toLowerCase();
    return index[type]
      .filter(record => (record[config.filter.key] ?? 0) >= threshold)
      .filter(record => !term || config.name(record).toLowerCase().includes(term) || String(record.id).includes(term))
      .sort((a, b) => config.rank(b) - config.rank(a));
  }, [index, type, query, threshold, config]);

  const visible = useMemo(() => matches.slice(0, LIST_LIMIT), [matches]);
  const drawable = useMemo(() => new Set(matches.slice(0, DRAW_LIMIT).map(record => record.id)), [matches]);

  const activeRecord = selected && selected.type === type ? records[type]?.get(selected.id) : null;
  const detailType = selected ? TYPES[selected.type] : null;
  const detailRecord = selected ? records[selected.type]?.get(selected.id) : null;

  const select = useCallback((nextType, id, moveMap = true) => {
    setSelected({ type: nextType, id });
    if (nextType !== type) setType(nextType);
    if (!moveMap) return;
    const collection = geo[nextType];
    if (!collection) return;
    const field = TYPES[nextType].idField;
    const feature = collection.features.find(item => item.properties[field] === id);
    if (feature) setFocus(L.geoJSON(feature).getBounds());
  }, [geo, type]);

  const relations = useMemo(() => {
    if (!detailRecord || !graph) return [];
    const list = [];
    const add = (kind, id, role) => {
      const record = records[kind]?.get(id);
      if (!id || !record) return;
      list.push({ kind, id, role, label: TYPES[kind].name(record), detail: TYPES[kind].detail(record) });
    };
    if (selected.type === 'rivers') {
      add('rivers', detailRecord.nextDown, 'Flows into');
      add('rivers', detailRecord.mainRiver, 'Main stem');
      (graph.upstream.get(detailRecord.id) || []).slice(0, 12).forEach(id => add('rivers', id, 'Feeder reach'));
      add('basins', detailRecord.basinId, 'Drains basin');
    } else if (selected.type === 'lakes') {
      add('basins', detailRecord.basinId, 'Sits in basin');
      (graph.basinRivers.get(detailRecord.basinId) || []).slice(0, 10).forEach(id => add('rivers', id, 'Basin reach'));
      (graph.basinLakes.get(detailRecord.basinId) || [])
        .filter(id => id !== detailRecord.id).slice(0, 6).forEach(id => add('lakes', id, 'Shares basin'));
    } else {
      add('basins', detailRecord.nextDown, 'Drains into');
      (graph.basinChildren.get(detailRecord.id) || []).slice(0, 10).forEach(id => add('basins', id, 'Upstream basin'));
      (graph.basinRivers.get(detailRecord.id) || []).slice(0, 12).forEach(id => add('rivers', id, 'Reach inside'));
      (graph.basinLakes.get(detailRecord.id) || []).slice(0, 8).forEach(id => add('lakes', id, 'Lake inside'));
    }
    return list;
  }, [detailRecord, graph, records, selected]);

  const metrics = useMemo(() => {
    if (!detailRecord) return [];
    if (selected.type === 'rivers') return [
      ['Reach length', `${num(detailRecord.lengthKm, 2)} km`],
      ['Strahler order', num(detailRecord.strahlerOrder)],
      ['Catchment', `${num(detailRecord.catchmentKm2, 2)} km²`],
      ['Upstream area', `${num(detailRecord.upstreamKm2, 1)} km²`],
      ['Mean discharge', `${num(detailRecord.dischargeCms, 3)} m³/s`],
      ['Distance to mouth', `${num(detailRecord.distanceDownKm, 1)} km`],
      ['Flow order', num(detailRecord.flowOrder)],
      ['Endorheic', detailRecord.endorheic ? 'Yes' : 'No'],
    ];
    if (selected.type === 'lakes') return [
      ['Surface area', `${num(detailRecord.areaKm2, 2)} km²`],
      ['Total volume', `${num(detailRecord.volumeMcm, 1)} MCM`],
      ['Average depth', `${num(detailRecord.depthM, 2)} m`],
      ['Elevation', `${num(detailRecord.elevationM)} m`],
      ['Mean discharge', `${num(detailRecord.dischargeCms, 3)} m³/s`],
      ['Lake type', num(detailRecord.lakeType)],
    ];
    return [
      ['Sub-basin area', `${num(detailRecord.areaKm2, 1)} km²`],
      ['In Uzbekistan', `${num(detailRecord.uzbekistanKm2, 1)} km²`],
      ['Share in country', `${num(detailRecord.uzbekistanPercent, 1)}%`],
      ['Upstream area', `${num(detailRecord.upstreamKm2, 1)} km²`],
      ['Pfafstetter', String(detailRecord.pfafId)],
      ['Endorheic', detailRecord.endorheic ? 'Yes' : 'No'],
    ];
  }, [detailRecord, selected]);

  if (error) return <div className="hydro-fatal">
    <h1>Hydrography index unavailable</h1>
    <p>{error}</p>
    <p>Rebuild the reference with npm run hydrography:build, then reload.</p>
    <a href="/">Return to the portal</a>
  </div>;

  if (!index) return <div className="hydro-loading"><LoaderCircle size={16}/> Loading hydrography index</div>;

  const activeGeo = geo[type];
  const drawn = activeGeo ? activeGeo.features.filter(feature => drawable.has(feature.properties[config.idField])).length : 0;
  const TypeIcon = config.icon;

  return <div className="hydro-app">
    <header className="hydro-header">
      <Logo/>
      <div className="hydro-header-title">
        <span>HYDROSHEDS REFERENCE</span>
        <strong>Hydrography explorer</strong>
      </div>
      <nav>
        <a href="/">Portal</a>
        <a href="/relationships.html">Tables</a>
        <a href="#workspace" className="active">Explorer</a>
        <a href="#database">Database</a>
      </nav>
    </header>

    <main className="hydro-main">
      <section className="hydro-overview">
        <div>
          <span className="hydro-kicker">RIVERS &middot; LAKES &middot; SUB-BASINS</span>
          <h1>Uzbekistan <span>water network</span></h1>
          <p>
            Every reach, lake and level-12 sub-basin clipped to the national boundary, together with the
            upstream and downstream links that connect them. Pick a record to trace what it drains into,
            what feeds it, and which basin holds it.
          </p>
        </div>
        <div className="hydro-stat-grid">
          <div><Waves size={19}/><strong>{num(index.counts.rivers)}</strong><span>River reaches</span></div>
          <div><Droplets size={19}/><strong>{num(index.counts.lakes)}</strong><span>Lakes</span></div>
          <div><Layers size={19}/><strong>{num(index.counts.basins)}</strong><span>Level-12 basins</span></div>
          <div><Network size={19}/><strong>{num(index.counts.downstreamLinks)}</strong><span>Downstream links</span></div>
        </div>
      </section>

      <section className="hydro-workspace" id="workspace">
        <div className="hydro-browser">
          <div className="hydro-panel-label">
            <Database size={13}/><span>RECORD BROWSER</span><small>{num(matches.length)} match</small>
          </div>
          <div className="hydro-type-tabs">
            {Object.entries(TYPES).map(([key, entry]) => {
              const Icon = entry.icon;
              return <button
                key={key}
                className={key === type ? 'active' : undefined}
                onClick={() => { setType(key); setQuery(''); }}
              ><Icon size={12}/>{entry.label}</button>;
            })}
          </div>
          <div className="hydro-search">
            <Search size={13}/>
            <input
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder={`Search ${config.plural} by name or id`}
              aria-label={`Search ${config.plural}`}
            />
          </div>
          <div className="hydro-order-filter">
            <span>{config.filter.label}</span>
            <strong>{config.filter.format(threshold)}</strong>
            <input
              type="range"
              min={config.filter.min}
              max={config.filter.max}
              step={config.filter.step}
              value={threshold}
              onChange={event => setThresholds(current => ({ ...current, [type]: Number(event.target.value) }))}
              aria-label={config.filter.label}
            />
          </div>
          <div className="hydro-record-list">
            {visible.map(record => <button
              key={record.id}
              className={activeRecord && activeRecord.id === record.id ? 'selected' : undefined}
              onClick={() => select(type, record.id)}
            >
              <i style={{ background: config.color }}/>
              <span><strong>{config.name(record)}</strong><small>{config.detail(record)}</small></span>
              <ChevronRight size={13}/>
            </button>)}
            {!visible.length && <div className="hydro-no-links">No {config.plural} match this filter.</div>}
          </div>
          <div className="hydro-list-more">
            Showing {num(visible.length)} of {num(matches.length)} {config.plural}, ranked by catchment size.
            Narrow the set with search or the slider above.
          </div>
        </div>

        <div className="hydro-map-shell">
          <MapContainer center={[41.5, 64.4]} zoom={5} minZoom={4} maxZoom={13} zoomControl={false} preferCanvas>
            <TileLayer
              attribution="&copy; OpenStreetMap contributors &copy; CARTO"
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            />
            <ZoomControl position="bottomleft"/>
            <ScaleControl position="topright"/>
            {geo.boundary && <GeoJSON
              key="boundary"
              data={geo.boundary}
              style={{ color: '#eee', weight: 1, fill: false, opacity: 0.75 }}
              interactive={false}
            />}
            {activeGeo && <GeoJSON
              key={`${type}-${threshold}-${query}-${activeRecord ? activeRecord.id : 'none'}`}
              data={activeGeo}
              filter={feature => drawable.has(feature.properties[config.idField])}
              style={feature => {
                const isSelected = activeRecord && feature.properties[config.idField] === activeRecord.id;
                return type === 'rivers'
                  ? { color: isSelected ? SELECTED_COLOR : config.color, weight: isSelected ? 3.5 : 0.9, opacity: isSelected ? 1 : 0.62 }
                  : {
                      color: isSelected ? SELECTED_COLOR : config.color,
                      weight: isSelected ? 2.5 : 0.7,
                      fillColor: isSelected ? SELECTED_COLOR : config.color,
                      fillOpacity: isSelected ? 0.4 : 0.16,
                    };
              }}
              onEachFeature={(feature, layer) => {
                layer.on('click', () => select(type, feature.properties[config.idField], false));
              }}
            />}
            <MapFocus bounds={focus}/>
          </MapContainer>
          <div className="hydro-map-meta">
            <span>UZBEKISTAN / WGS 84</span>
            <span><strong>{num(drawn)} DRAWN</strong></span>
          </div>
          <div className="hydro-map-legend">
            <span><i style={{ background: config.color }}/>{config.label}</span>
            <span><i className="selected"/>Selected</span>
            <span><i className="boundary"/>Boundary</span>
          </div>
          {(loadingGeo && !activeGeo) && <div className="hydro-map-loading"><LoaderCircle size={15}/> Loading {config.label} geometry</div>}
        </div>

        <div className="hydro-details">
          <div className="hydro-panel-label">
            <Share2 size={13}/><span>RELATIONSHIPS</span><small>{detailRecord ? `${relations.length} links` : 'no selection'}</small>
          </div>
          {detailRecord ? <div className="hydro-detail-content">
            <div className="hydro-entity-heading">
              <span style={{ color: detailType.color }}>{detailType.label.toUpperCase()}</span>
              <small>ID {detailRecord.id}</small>
            </div>
            <h2>{detailType.name(detailRecord)}</h2>
            <p>{detailType.detail(detailRecord)} &middot; clipped to the Uzbekistan ADM0 boundary.</p>
            <div className="hydro-metrics">
              {metrics.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
            </div>
            <div className="hydro-relation-title">
              <Network size={13}/><span>CONNECTED RECORDS</span><small>{relations.length}</small>
            </div>
            {relations.length ? <div className="hydro-relation-list">
              {relations.map((relation, position) => {
                const Icon = TYPES[relation.kind].icon;
                return <button
                  key={`${relation.role}-${relation.kind}-${relation.id}-${position}`}
                  className="hydro-relation-link"
                  style={{ '--relation-color': TYPES[relation.kind].color }}
                  onClick={() => select(relation.kind, relation.id)}
                >
                  <i><Icon size={13}/></i>
                  <span><strong>{relation.role} &middot; {relation.label}</strong><small>{relation.detail}</small></span>
                  <ArrowUpRight size={13}/>
                </button>;
              })}
            </div> : <div className="hydro-no-links">
              This record is a terminal node in the clipped network &mdash; nothing it connects to stays inside Uzbekistan.
            </div>}
          </div> : <div className="hydro-empty-detail">
            <MapPin size={30}/>
            <div>Select a {config.singular} from the browser or the map to trace its upstream and downstream links.</div>
          </div>}
        </div>
      </section>

      <section className="hydro-database-note" id="database">
        <div>
          <span className="hydro-kicker">PROVENANCE</span>
          <TypeIcon size={26} color={config.color}/>
        </div>
        <div>
          <h2>Built from HydroSHEDS</h2>
          <p>
            Rivers come from HydroRIVERS v1.0, lakes from HydroLAKES v1.0 and sub-basins from HydroBASINS
            level 12, each intersected with the Uzbekistan ADM0 boundary. Rebuild with
            {' '}<code>npm run hydrography:build</code>, which writes both the GeoPackage under
            {' '}<code>storage/derived/hydrography</code> and the web layers this page reads.
          </p>
          <p>Generated {new Date(index.generatedAt).toLocaleString('en-GB')} &middot; {index.selection}.</p>
        </div>
        <div className="hydro-schema">
          {['rivers_uzbekistan', 'lakes_uzbekistan', 'basins_level12', 'river_downstream_links', 'river_basin_links', 'lake_basin_links']
            .map(table => <span key={table}>{table}</span>)}
        </div>
      </section>
    </main>

    <footer className="hydro-footer">
      <Logo/>
      <span>HYDROSHEDS &middot; HYDROLAKES &middot; CLIPPED TO UZBEKISTAN</span>
      <a href="/">Back to the portal <ArrowUpRight size={13}/></a>
    </footer>
  </div>;
}
