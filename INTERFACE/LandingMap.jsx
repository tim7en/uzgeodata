import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CircleMarker, GeoJSON, MapContainer, ScaleControl, TileLayer, Tooltip, ZoomControl, useMap, useMapEvent } from 'react-leaflet';
import { ArrowUpRight, Droplets, Layers, Search, X } from 'lucide-react';
import DamModal from './DamModal.jsx';
import {
  HEADLINE_ATTRIBUTES, SYSTEMS, basinHeadline, basinStyle,
  clusterDams, damClusterBounds, damClusterStyle,
  damLabel, damLegendStops, damStyle, damTotals,
  formatAttribute, formatNumber, groupAttributes, indexStore, legendStops, levelForZoom,
  overlayStyle, quantileBreaks, readAttribute, riverStyle, systemMeta, systemTotals, tierForZoom,
} from './landingModel.js';

const LADDER_URL = '/data/hydroclimate/reference-basin-levels.json';
const RIVER_LADDER_URL = '/data/hydroclimate/reference-river-levels.json';
const GROUPS_URL = '/data/hydroclimate/reference-attribute-groups.json';
const CATALOGUE_URL = '/data/hydroclimate/reference-attribute-catalogue.json';
const DAMS_URL = '/data/hydroclimate/dams-transboundary.geojson';
const CENTRE = [40.2, 70.5];
const DEEPER = [
  { href: '/case-studies.html', label: 'Chirchik case studies', note: 'Precipitation, temperature and discharge validation' },
  { href: '/climate.html', label: 'Hydroclimate observatory', note: 'Snow, precipitation and anomalies by basin' },
  { href: '/ontology.html', label: 'Living ontology', note: 'Trace a basin upstream and downstream' },
  { href: '/hydrography.html', label: 'Hydrography explorer', note: 'Rivers, lakes and basin attributes' },
  { href: '/metadata.html', label: 'Attribute catalogue', note: 'Source, citation and licence for all 281 attributes' },
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

const GROUP_ORDER = ['basin_specific', 'basin_accumulation'];

/**
 * The whole related dataset for one watershed, as a table.
 *
 * 281 rows never fitted a 340px rail, so the panel now opens this instead: one
 * scrollable table, filterable, with each row carrying the source product and
 * licence it came from and whether it describes this sub-basin or everything
 * upstream of it.
 */
function AttributeModal({ basin, groups, store, catalogue, loading, onClose }) {
  const [filter, setFilter] = useState('');
  const [kind, setKind] = useState('all');

  useEffect(() => {
    const escape = event => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [onClose]);

  const rows = useMemo(() => {
    const term = filter.trim().toLowerCase();
    const collected = [];
    for (const groupId of GROUP_ORDER) {
      if (kind !== 'all' && kind !== groupId) continue;
      for (const category of groupAttributes(groups, store, basin.hybas_id, groupId)) {
        for (const attribute of category.attributes) {
          if (term && !attribute.label.toLowerCase().includes(term)
            && !attribute.column.includes(term)
            && !category.id.toLowerCase().includes(term)) continue;
          const code = catalogue?.columnIndex?.[attribute.column]?.variable;
          const variable = catalogue?.variables?.find(entry => entry.code === code);
          collected.push({ ...attribute, category: category.id, groupId, variable });
        }
      }
    }
    return collected;
  }, [groups, store, catalogue, basin.hybas_id, filter, kind]);

  return <div className="land-modal" role="dialog" aria-modal="true" aria-label="Atlas attributes for this basin"
    onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section>
      <header>
        <div>
          <span>{systemMeta(basin.system_id).label} · level {basin.basin_level}</span>
          <h2>HYBAS {basin.hybas_id}</h2>
          <p>{formatNumber(basin.area_km2)} km² in this sub-basin · {formatNumber(basin.upstream_km2)} km² upstream</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close"><X size={15}/></button>
      </header>

      <div className="land-modal-tools">
        <label><Search size={12}/><input value={filter} onChange={event => setFilter(event.target.value)}
          placeholder="Attribute, category or column"/></label>
        <div className="land-modal-kinds">
          {[['all', 'All'], ['basin_specific', 'This sub-basin'], ['basin_accumulation', 'Upstream']].map(([id, label]) =>
            <button key={id} type="button" className={kind === id ? 'active' : ''} onClick={() => setKind(id)}>{label}</button>)}
        </div>
        <span>{formatNumber(rows.length)} attributes</span>
      </div>

      <div className="land-modal-scroll">
        {loading && !store ? <p className="land-group-note">Loading the atlas attributes…</p>
          : <table>
            <thead><tr>
              <th>Attribute</th><th>Value</th><th>Measured over</th><th>Category</th><th>Source</th>
            </tr></thead>
            <tbody>{rows.map(row => <tr key={row.column}>
              <td><strong>{row.label}</strong><code>{row.column}</code></td>
              <td className="land-modal-value">{row.value}{row.unit ? <em> {row.unit}</em> : null}</td>
              <td><span className={`land-kind ${row.groupId}`}>{row.spatialExtentLabel}</span></td>
              <td>{row.category}</td>
              <td className="land-modal-source">
                {row.variable?.source || '—'}
                {row.variable?.licence ? <small>{row.variable.licence}</small> : null}
              </td>
            </tr>)}</tbody>
          </table>}
        {!rows.length && store ? <p className="land-group-note">Nothing matches that filter.</p> : null}
      </div>

      <footer>
        <span>Values join on <code>hybas_id</code>; river reaches inherit through <code>HYBAS_L12</code>.</span>
        <a href="/metadata.html">Full attribute catalogue <ArrowUpRight size={11}/></a>
      </footer>
    </section>
  </div>;
}

export default function LandingMap() {
  const [ladder, setLadder] = useState(null);
  const [riverLadder, setRiverLadder] = useState(null);
  const [levels, setLevels] = useState({});
  const [riverTiers, setRiverTiers] = useState({});
  const [zoom, setZoom] = useState(6);
  const [groups, setGroups] = useState(null);
  const [storeRequested, setStoreRequested] = useState(false);
  const [loadingStore, setLoadingStore] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [hoveredId, setHoveredId] = useState(null);
  const [query, setQuery] = useState('');
  const [overlay, setOverlay] = useState('');
  const [tableOpen, setTableOpen] = useState(false);
  const [catalogue, setCatalogue] = useState(null);
  const [bounds, setBounds] = useState(null);
  const [dams, setDams] = useState(null);
  const [showDams, setShowDams] = useState(true);
  const [dam, setDam] = useState(null);
  const layersById = useRef(new Map());
  const painted = useRef([]);
  const drawnLevel = useRef(null);
  const inFlight = useRef(new Set());

  useEffect(() => {
    let live = true;
    Promise.all([json(LADDER_URL), json(RIVER_LADDER_URL), json(GROUPS_URL)])
      .then(([ladderDocument, riverDocument, groupDocument]) => {
        if (!live) return;
        setLadder(ladderDocument);
        setRiverLadder(riverDocument);
        setGroups(groupDocument);
      })
      .catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, []);


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

  useEffect(() => {
    if (!showDams || dams) return undefined;
    let live = true;
    // The dam layer is an overlay on the landing map, not its subject: a failure
    // switches the layer off rather than replacing the map with an error page.
    json(DAMS_URL).then(document => live && setDams(document)).catch(() => live && setShowDams(false));
    return () => { live = false; };
  }, [showDams, dams]);

  const damStats = useMemo(() => (dams ? damTotals(dams.features) : null), [dams]);
  // Recomputed on every zoom change: this is what regroups the dams as the reader
  // moves in. A hundred points is small enough that the whole grid is rebuilt
  // rather than updated incrementally.
  const damClusters = useMemo(
    () => (showDams && dams ? clusterDams(dams.features, zoom) : []),
    [showDams, dams, zoom],
  );

  // Attributes are fetched per level, and only once a reader asks for them —
  // either by opening a group in the panel or by colouring the map.
  const [stores, setStores] = useState({});
  const store = active ? stores[active.level] : null;
  // HydroBASINS id spaces do not overlap between levels, so a level-7 id looked up
  // in the level-10 store resolves to nothing at all. The panel therefore reads the
  // store of the level the *selected* basin belongs to, which is not always the
  // level being drawn — a selection is deliberately held when the reader zooms past
  // it. Both stores are fetched when they differ.
  const selectedLevel = selected ? Number(selected.properties.basin_level) : null;
  const detailStore = selectedLevel ? stores[selectedLevel] || null : null;
  const wantedLevels = useMemo(() => {
    const levels = new Set();
    if (overlay && active) levels.add(active.level);
    if (storeRequested && selectedLevel) levels.add(selectedLevel);
    return [...levels];
  }, [overlay, active, storeRequested, selectedLevel]);

  // The in-flight set lives in a ref rather than in state on purpose. Guarding on
  // `loadingStore` made the effect depend on a value it sets itself: flipping the
  // flag re-ran the effect, whose cleanup cancelled the very fetch that had just
  // started, so the panel waited on a request that could never resolve.
  useEffect(() => {
    const pending = wantedLevels.filter(level => !stores[level] && !inFlight.current.has(level));
    if (!pending.length) return;
    for (const level of pending) {
      const entry = ladder?.levels?.find(item => item.level === level);
      if (!entry) continue;
      inFlight.current.add(level);
      setLoadingStore(true);
      json(entry.attributesUrl)
        .then(document => setStores(current => ({ ...current, [level]: indexStore(document) })))
        .catch(cause => setError(cause.message))
        .finally(() => {
          inFlight.current.delete(level);
          setLoadingStore(inFlight.current.size > 0);
        });
    }
  }, [wantedLevels, stores, ladder]);

  useEffect(() => {
    if (!tableOpen || catalogue) return;
    json(CATALOGUE_URL).then(setCatalogue).catch(cause => setError(cause.message));
  }, [tableOpen, catalogue]);

  const tier = useMemo(() => tierForZoom(zoom, riverLadder), [zoom, riverLadder]);
  const rivers = tier ? riverTiers[tier.id] : null;

  useEffect(() => {
    if (!tier || riverTiers[tier.id]) return undefined;
    let live = true;
    json(tier.url)
      .then(document => live && setRiverTiers(current => ({ ...current, [tier.id]: document })))
      .catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, [tier, riverTiers]);

  const overlayMeta = useMemo(() => {
    if (!overlay || !groups) return null;
    for (const group of groups.groups) {
      for (const category of group.categories) {
        const found = category.attributes.find(attribute => attribute.column === overlay);
        if (found) return { ...found, group: group.id, category: category.id };
      }
    }
    return null;
  }, [overlay, groups]);
  const overlayValues = overlay && store ? store.values?.[overlay] || null : null;
  const overlayBreaks = useMemo(() => (overlayValues ? quantileBreaks(overlayValues) : []), [overlayValues]);
  const legend = useMemo(() => legendStops(overlayBreaks), [overlayBreaks]);

  const styleFor = useCallback((properties, state) => {
    if (!overlay || !store) return basinStyle(properties, state);
    return overlayStyle(properties, state, readAttribute(store, properties.hybas_id, overlay), overlayBreaks);
  }, [overlay, store, overlayBreaks]);

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

  // Swapping level mounts a fresh set of Leaflet layers, so the registry is
  // emptied here, during render, before onEachFeature refills it. Doing it in an
  // effect ran after that and wiped the new layers instead of the old ones.
  if (drawnLevel.current !== active?.level) {
    layersById.current = new Map();
    painted.current = [];
    drawnLevel.current = active?.level;
  }

  // Restyling the whole collection on every pointer move would repaint 7,445
  // polygons; only the shape being left and the one being entered change.
  const restyle = useCallback((id, state) => {
    const layer = layersById.current.get(id);
    if (layer) layer.setStyle(styleFor(layer.feature.properties, state));
  }, [styleFor]);

  useEffect(() => {
    const previous = painted.current;
    for (const id of new Set([...previous, hoveredId, selectedId].filter(Boolean))) {
      restyle(id, { hovered: id === hoveredId, selected: id === selectedId });
    }
    painted.current = [hoveredId, selectedId].filter(Boolean);
  }, [selectedId, hoveredId, restyle, basins]);

  // Changing the coloured attribute repaints every drawn basin once.
  useEffect(() => {
    for (const [id, layer] of layersById.current) {
      layer.setStyle(styleFor(layer.feature.properties, { selected: id === selectedId, hovered: id === hoveredId }));
    }
  }, [styleFor, basins, selectedId, hoveredId]);


  const onEachFeature = useCallback((feature, layer) => {
    const id = String(feature.properties.hybas_id);
    layersById.current.set(id, layer);
    layer.on({
      mouseover: () => setHoveredId(id),
      mouseout: () => setHoveredId(current => (current === id ? null : current)),
      click: () => { setSelected(feature); setDam(null); setQuery(''); },
    });
  }, []);

  const focus = feature => {
    setSelected(feature);
    setDam(null);
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
        style={feature => styleFor(feature.properties, {})} onEachFeature={onEachFeature}/>}
      {rivers && <GeoJSON key={`rivers-${tier.id}`} data={rivers} style={feature => riverStyle(feature.properties)}
        interactive={false} smoothFactor={1.2}/>}
      {/* The dams go in the marker pane, not the overlay pane the basins use:
          Leaflet hands a canvas click to whichever layer joined that renderer
          last, and the basin GeoJSON remounts on every level change, so sharing
          a renderer with it makes the dams stop responding at unpredictable
          moments. Their own pane settles stacking and hit order together. */}
      {damClusters.map(cluster => {
        if (cluster.count === 1) {
          const feature = cluster.members[0];
          const state = { selected: dam?.dam_id === feature.properties.dam_id };
          return <CircleMarker key={`dam-${feature.properties.dam_id}`} pane="markerPane"
            center={[cluster.latitude, cluster.longitude]}
            pathOptions={damStyle(feature.properties, state)}
            radius={damStyle(feature.properties, state).radius}
            eventHandlers={{ click: () => { setDam(feature.properties); setSelected(null); } }}>
            <Tooltip direction="top" offset={[0, -4]} opacity={1} className="land-dam-tip">
              {damLabel(feature.properties)}
            </Tooltip>
          </CircleMarker>;
        }
        return <CircleMarker key={`group-${cluster.key}`} pane="markerPane"
          center={[cluster.latitude, cluster.longitude]}
          pathOptions={damClusterStyle(cluster)}
          radius={damClusterStyle(cluster).radius}
          eventHandlers={{ click: () => setBounds(damClusterBounds(cluster)) }}>
          {/* One tooltip per layer: Leaflet replaces a layer's tooltip when a
              second is bound, so a group carries only its permanent count. The
              hover feedback is the ring in damClusterStyle, and the detail is
              one click away. */}
          <Tooltip permanent direction="center" className="land-dam-count">{cluster.count}</Tooltip>
        </CircleMarker>;
      })}
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
      {basins && groups && <section className="land-overlay">
        <label>
          <span>Colour basins by</span>
          <select value={overlay} onChange={event => setOverlay(event.target.value)}>
            <option value="">River system</option>
            {HEADLINE_ATTRIBUTES.map(column => {
              const meta = attributeMeta(groups, column);
              return meta ? <option key={column} value={column}>{meta.label}</option> : null;
            })}
          </select>
        </label>
        {overlay && !store && <p className="land-group-note">Loading level {active.level} attributes…</p>}
        {overlay && legend.length > 0 && <div className="land-legend">
          <span>{overlayMeta?.units || ''}</span>
          <ol>{legend.map((stop, index) => <li key={index}>
            <i style={{ background: stop.color }}/>
            <em>{stop.from === null ? `< ${formatAttribute(stop.to, overlayMeta?.units).value}`
              : stop.to === null ? `≥ ${formatAttribute(stop.from, overlayMeta?.units).value}`
                : `${formatAttribute(stop.from, overlayMeta?.units).value} – ${formatAttribute(stop.to, overlayMeta?.units).value}`}</em>
          </li>)}</ol>
          <a href={`/atlas.html?attribute=${overlay}`}>Open in the atlas explorer <ArrowUpRight size={11}/></a>
        </div>}

        <div className="land-dams">
          <label className="land-toggle">
            <input type="checkbox" checked={showDams} onChange={event => {
              setShowDams(event.target.checked);
              if (!event.target.checked) setDam(null);
            }}/>
            <Droplets size={12}/>
            <span>Dams and reservoirs</span>
          </label>
          {showDams && damStats && <>
            <ul className="land-sizekey">
              {damLegendStops().map(stop => <li key={stop.capacity}>
                <i style={{ width: stop.radius * 2, height: stop.radius * 2 }}/>
                <em>{formatNumber(stop.capacity)}</em>
              </li>)}
            </ul>
            <p className="land-group-note">
              {damStats.dams} barriers holding {formatNumber(damStats.storageMcm)} MCM. Circle width
              follows storage on a logarithmic scale, in MCM; a hollow ring is a barrier whose
              capacity the source never reported.
            </p>
          </>}
          {showDams && !damStats && <p className="land-group-note">Loading dams…</p>}
        </div>
      </section>}
      {basins && <p className="land-level">
        Level {active.level} · {formatNumber(features.length)} basins
        {rivers ? ` · ${formatNumber(rivers.features.length)} reaches` : ''}
        {selected && Number(selected.properties.basin_level) !== active.level
          ? ` · selection held at level ${selected.properties.basin_level}` : ''}
      </p>}
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
        <span className="land-kicker">{systemMeta(selected.properties.system_id).label} · level {selected.properties.basin_level}</span>
        <h2>HYBAS {selected.properties.hybas_id}</h2>
        <dl className="land-headline">{basinHeadline(selected.properties).map(row => <div key={row.label}>
          <dt>{row.label}</dt>
          <dd>{row.value}{row.unit ? <em> {row.unit}</em> : null}</dd>
        </div>)}</dl>
        <button type="button" className="land-open-table" onClick={() => { setStoreRequested(true); setTableOpen(true); }}>
          <span>
            <strong>Atlas attributes</strong>
            <small>{groups?.groups?.reduce((total, group) => total + group.attributeCount, 0) || 281} measured values for this watershed</small>
          </span>
          <ArrowUpRight size={13}/>
        </button>
        <p className="land-note">Upstream values already account for everything above this basin. They cannot be added together across basins.</p>
      </div>}

      <nav className="land-deeper">
        <span><Layers size={12}/> Go deeper</span>
        {DEEPER.map(item => <a key={item.href} href={item.href}>
          <span><strong>{item.label}</strong><small>{item.note}</small></span>
          <ArrowUpRight size={13}/>
        </a>)}
      </nav>
    </aside>

    {tableOpen && selected && <AttributeModal basin={selected.properties} groups={groups} store={detailStore}
      catalogue={catalogue} loading={loadingStore} onClose={() => setTableOpen(false)}/>}

    {dam && <DamModal dam={dam} onClose={() => setDam(null)}/>}
  </main>;
}

function attributeMeta(groups, column) {
  for (const group of groups?.groups || []) {
    for (const category of group.categories) {
      const found = category.attributes.find(attribute => attribute.column === column);
      if (found) return found;
    }
  }
  return null;
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
