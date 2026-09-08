import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { GeoJSON, MapContainer, ScaleControl, TileLayer, ZoomControl, useMap, useMapEvent } from 'react-leaflet';
import { ArrowUpRight, ChevronDown, Layers, Search, X } from 'lucide-react';
import {
  SYSTEMS, basinHeadline, basinStyle, carriesAttributes, formatNumber, groupAttributes,
  groupSummary, indexStore, levelForZoom, systemMeta, systemTotals,
} from './landingModel.js';

const LADDER_URL = '/data/hydroclimate/reference-basin-levels.json';
const GROUPS_URL = '/data/hydroclimate/reference-attribute-groups.json';
const ATTRIBUTES_URL = '/data/hydroclimate/reference-basin-attributes.json';
const CENTRE = [40.2, 70.5];
const DEEPER = [
  { href: '/climate.html', label: 'Hydroclimate observatory', note: 'Snow, precipitation and anomalies by basin' },
  { href: '/ontology.html', label: 'Living ontology', note: 'Trace a basin upstream and downstream' },
  { href: '/hydrography.html', label: 'Hydrography explorer', note: 'Rivers, lakes and basin attributes' },
  { href: '/catalogue.html', label: 'Data catalogue', note: 'Every published dataset and its currency' },
  { href: '/portal.html', label: 'Portal overview', note: 'Atlas packages, use cases and standards' },
];

const json = url => fetch(url).then(response => response.ok
  ? response.json()
  : Promise.reject(new Error(`${response.status} while loading ${url}`)));

function WatchZoom({ onZoom }) {
  useMapEvent('zoomend', event => onZoom(event.target.getZoom()));
  return null;
}

function FitTo({ bounds }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) map.flyToBounds(bounds, { padding: [40, 40], duration: 0.8 });
  }, [bounds, map]);
  return null;
}

function AttributeGroup({ groups, store, hybasId, groupId, loading, onOpen }) {
  const [open, setOpen] = useState(false);
  const summary = groupSummary(groups, groupId);
  const categories = open && store ? groupAttributes(groups, store, hybasId, groupId) : [];
  return <section className={`land-group ${open ? 'open' : ''}`}>
    <button type="button" onClick={() => { setOpen(current => !current); if (!open) onOpen(); }}>
      <span><strong>{summary.label}</strong><small>{summary.attributeCount} attributes · {summary.categories} categories</small></span>
      <ChevronDown size={14}/>
    </button>
    {open && (loading ? <p className="land-group-note">Loading the atlas attributes…</p>
      : categories.map(category => <div className="land-category" key={category.id}>
        <span>{category.id}</span>
        <dl>{category.attributes.map(attribute => <div key={attribute.column}>
          <dt title={attribute.label}>{attribute.label}</dt>
          <dd>{attribute.value}{attribute.unit ? <em> {attribute.unit}</em> : null}</dd>
        </div>)}</dl>
      </div>))}
  </section>;
}

export default function LandingMap() {
  const [ladder, setLadder] = useState(null);
  const [levels, setLevels] = useState({});
  const [zoom, setZoom] = useState(6);
  const [groups, setGroups] = useState(null);
  const [store, setStore] = useState(null);
  const [loadingStore, setLoadingStore] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [hoveredId, setHoveredId] = useState(null);
  const [query, setQuery] = useState('');
  const [bounds, setBounds] = useState(null);
  const layersById = useRef(new Map());
  const painted = useRef([]);

  useEffect(() => {
    let live = true;
    Promise.all([json(LADDER_URL), json(GROUPS_URL)])
      .then(([ladderDocument, groupDocument]) => {
        if (!live) return;
        setLadder(ladderDocument);
        setGroups(groupDocument);
      })
      .catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, []);

  // Six megabytes of attributes are worth fetching only once somebody asks to
  // see them, which is why the map itself carries just the headline fields.
  const loadStore = useCallback(() => {
    if (store || loadingStore) return;
    setLoadingStore(true);
    json(ATTRIBUTES_URL)
      .then(document => setStore(indexStore(document)))
      .catch(cause => setError(cause.message))
      .finally(() => setLoadingStore(false));
  }, [store, loadingStore]);

  const active = useMemo(() => levelForZoom(zoom, ladder), [zoom, ladder]);
  const basins = active ? levels[active.level] : null;

  // Each level is fetched once, the first time the reader zooms into it.
  useEffect(() => {
    if (!active || levels[active.level]) return undefined;
    let live = true;
    json(active.url)
      .then(document => live && setLevels(current => ({ ...current, [active.level]: document })))
      .catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, [active, levels]);

  const features = basins?.features || [];
  const byId = useMemo(() => new Map(features.map(feature => [String(feature.properties.hybas_id), feature])), [features]);
  const totals = useMemo(() => systemTotals(features), [features]);
  const selectedId = selected ? String(selected.properties.hybas_id) : null;
  const results = useMemo(() => {
    const term = query.trim();
    if (term.length < 3) return [];
    return features
      .filter(feature => String(feature.properties.hybas_id).includes(term)
        || String(feature.properties.pfaf_id).includes(term))
      .slice(0, 6);
  }, [query, features]);

  // Restyling the whole collection on every pointer move would repaint 7,445
  // polygons; only the shape being left and the one being entered change.
  const restyle = useCallback((id, state) => {
    const layer = layersById.current.get(id);
    if (layer) layer.setStyle(basinStyle(layer.feature.properties, state));
  }, []);

  useEffect(() => {
    const previous = painted.current;
    for (const id of new Set([...previous, hoveredId, selectedId].filter(Boolean))) {
      restyle(id, { hovered: id === hoveredId, selected: id === selectedId });
    }
    painted.current = [hoveredId, selectedId].filter(Boolean);
  }, [selectedId, hoveredId, restyle]);

  useEffect(() => { layersById.current = new Map(); painted.current = []; }, [active?.level]);

  const onEachFeature = useCallback((feature, layer) => {
    const id = String(feature.properties.hybas_id);
    layersById.current.set(id, layer);
    layer.on({
      mouseover: () => setHoveredId(id),
      mouseout: () => setHoveredId(current => (current === id ? null : current)),
      click: () => { setSelected(feature); setQuery(''); },
    });
  }, []);

  const focus = feature => {
    setSelected(feature);
    setQuery('');
    setBounds(featureBounds(feature));
  };

  const focusSystem = system => {
    const members = features.filter(feature => feature.properties.system_id === system);
    if (members.length) setBounds(collectionBounds(members));
  };

  if (error) return <main className="land-state"><h1>The map could not load.</h1><p>{error}</p></main>;

  return <main className="land">
    <MapContainer center={CENTRE} zoom={6} zoomControl={false} className="land-map" preferCanvas>
      <TileLayer attribution="&copy; OpenStreetMap contributors"
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" opacity={0.42}/>
      {basins && <GeoJSON key={active.level} data={basins} smoothFactor={1.6}
        style={feature => basinStyle(feature.properties, {})} onEachFeature={onEachFeature}/>}
      <FitTo bounds={bounds}/>
      <WatchZoom onZoom={setZoom}/>
      <ZoomControl position="bottomright"/>
      <ScaleControl position="bottomright" imperial={false}/>
    </MapContainer>

    <header className="land-head">
      <div>
        <span>UZGEODATA</span>
        <h1>Where the water forms</h1>
      </div>
      <p>Amu Darya and Syr Darya as they drain, not as borders cut them. Pick any sub-basin to read it.</p>
    </header>

    <aside className={`land-panel ${selected ? 'has-selection' : ''}`}>
      {!basins && <p className="land-loading">Loading the reference basins…</p>}
      {basins && <p className="land-level">Level {active.level} · {formatNumber(features.length)} basins in view</p>}
      {basins && !selected && <div className="land-intro">
        <label className="land-search">
          <Search size={13}/>
          <input value={query} onChange={event => setQuery(event.target.value)} placeholder="HYBAS or PFAF id"/>
        </label>
        {results.length > 0 && <div className="land-results">{results.map(feature => <button key={feature.properties.hybas_id}
          type="button" onClick={() => focus(feature)}>
          <strong>{feature.properties.hybas_id}</strong>
          <small>{systemMeta(feature.properties.system_id).label} · {formatNumber(feature.properties.area_km2)} km²</small>
        </button>)}</div>}
        <p className="land-hint">Or start from a system.</p>
        <div className="land-systems">{totals.map(entry => <button key={entry.system} type="button"
          onClick={() => focusSystem(entry.system)} style={{ '--system': systemMeta(entry.system).color }}>
          <i/>
          <span>
            <strong>{systemMeta(entry.system).label}</strong>
            <small>{formatNumber(entry.units)} basins · {formatNumber(entry.areaKm2)} km²</small>
          </span>
        </button>)}</div>
      </div>}

      {selected && <div className="land-detail" style={{ '--system': systemMeta(selected.properties.system_id).color }}>
        <button type="button" className="land-close" onClick={() => setSelected(null)} aria-label="Clear selection"><X size={14}/></button>
        <span className="land-kicker">{systemMeta(selected.properties.system_id).label} · level 12</span>
        <h2>HYBAS {selected.properties.hybas_id}</h2>
        <dl className="land-headline">{basinHeadline(selected.properties).map(row => <div key={row.label}>
          <dt>{row.label}</dt>
          <dd>{row.value}{row.unit ? <em> {row.unit}</em> : null}</dd>
        </div>)}</dl>
        {carriesAttributes(selected.properties, ladder) ? <>
          <AttributeGroup groups={groups} store={store} hybasId={selected.properties.hybas_id}
            groupId="basin_specific" loading={loadingStore} onOpen={loadStore}/>
          <AttributeGroup groups={groups} store={store} hybasId={selected.properties.hybas_id}
            groupId="basin_accumulation" loading={loadingStore} onOpen={loadStore}/>
          <p className="land-note">Upstream values already account for everything above this basin. They cannot be added together across basins.</p>
        </> : <p className="land-note">The {groups?.groups?.reduce((total, group) => total + group.attributeCount, 0) || 281} atlas attributes are published on level {ladder?.attributeLevel}. Zoom in to reach them.</p>}
      </div>}

      <nav className="land-deeper">
        <span><Layers size={12}/> Go deeper</span>
        {DEEPER.map(item => <a key={item.href} href={item.href}>
          <span><strong>{item.label}</strong><small>{item.note}</small></span>
          <ArrowUpRight size={13}/>
        </a>)}
      </nav>
    </aside>
  </main>;
}

function coordinates(geometry) {
  if (!geometry) return [];
  if (geometry.type === 'Polygon') return geometry.coordinates.flat();
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.flat(2);
  return [];
}

function featureBounds(feature) {
  return collectionBounds([feature]);
}

function collectionBounds(features) {
  let minLat = Infinity, maxLat = -Infinity, minLon = Infinity, maxLon = -Infinity;
  for (const feature of features) {
    for (const [lon, lat] of coordinates(feature.geometry)) {
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
      if (lon < minLon) minLon = lon;
      if (lon > maxLon) maxLon = lon;
    }
  }
  return Number.isFinite(minLat) ? [[minLat, minLon], [maxLat, maxLon]] : null;
}

export { SYSTEMS };
