import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ThemeToggle, { useTheme } from './ThemeToggle.jsx';
import { CircleMarker, GeoJSON, MapContainer, ScaleControl, TileLayer, Tooltip, ZoomControl, useMap, useMapEvent } from 'react-leaflet';
import { ArrowUpRight, BookOpen, Droplets, Layers, Search, X } from 'lucide-react';
import { mountSelect } from './lang.js';
import DamModal from './DamModal.jsx';
import { svg } from 'leaflet';
import LakeLayer from './LakeLayer.jsx';
import LakeModal from './LakeModal.jsx';
import StationLayer from './StationLayer.jsx';
import StationModal from './StationModal.jsx';
import GaugeModal from './GaugeModal.jsx';
import BasinSubstitutes from './BasinSubstitutes.jsx';
import BasinHistory from './BasinHistory.jsx';
import { AoiLayer, AoiPanel } from './AoiTool.jsx';
import { selectBasins } from './aoiModel.js';
import { DEFAULT_MAP_VIEW, readMapView, saveMapView, collectionBounds } from './mapViewModel.js';
import {
  HEADLINE_ATTRIBUTES, SYSTEMS, basinHeadline, basinStyle,
  clusterDams, damClusterBounds, damClusterStyle,
  damLabel, damLegendStops, damStyle, damTotals,
  OVERLAY_OPACITY, formatAttribute, formatNumber, groupAttributes, indexStore, legendStops, levelForZoom,
  overlayOpacity, overlayStyle, quantileBreaks, readAttribute, riverStyle, systemMeta, systemTotals, tierForZoom,
} from './landingModel.js';

const LADDER_URL = '/data/hydroclimate/reference-basin-levels.json';
const RIVER_LADDER_URL = '/data/hydroclimate/reference-river-levels.json';
const GROUPS_URL = '/data/hydroclimate/reference-attribute-groups.json';
const CATALOGUE_URL = '/data/hydroclimate/reference-attribute-catalogue.json';
const DAMS_URL = '/data/hydroclimate/dams-transboundary.geojson';
const OPACITY_KEY = 'uzgeodata.overlayOpacity';
const PANEL_CLOSE_DELAY = 650;
// How much of each corner the fixed UI takes up, in pixels, so a fitted view
// never lands a basin under the sidebar, the header or the zoom controls.
const OCCLUDED_TOP_LEFT = [300, 170];
const OCCLUDED_BOTTOM_RIGHT = [40, 110];
const DEEPER = [
  { href: '/data-lineage.html', label: 'Data lineage & updates', note: 'Source tree, coverage gaps and refresh classes' },
  { href: '/dynamic-atlas.html', label: 'Dynamic HydroATLAS', note: 'Earth Engine results, resolution and updates' },
  { href: '/roadmap.html', label: 'Atlas roadmap', note: 'Methods, reproduction and basin history' },
  { href: '/case-studies.html', label: 'Case studies', note: 'Runoff models and station–satellite work' },
  { href: '/research.html', label: 'Research foundations', note: 'Published research bound to layers 1–4' },
];

// Public reading support is available without loading the map or a data bundle.
const PROGRAMME = [
  { id: 'overview', label: 'Project overview', note: 'Purpose, coverage and research direction', href: '/project.html' },
  { id: 'usecases', label: 'Use cases', note: 'Practical workflows and direct downloads', href: '/examples.html' },
  { id: 'about', label: 'About & citation', note: 'Public preview, sources and reuse', href: '/about.html' },
  { id: 'support', label: 'User guide', note: 'Read a basin in five minutes', href: '/guide.html' },
  { id: 'projects', label: 'Projects', note: 'Available studies and future work', href: '/projects.html' },
];

// The three readings of one basin: what the atlas published, what this project
// estimates independently, and the dated record those estimates were derived from.
const TABS = [
  ['original', 'HydroATLAS attributes'],
  ['substitutes', 'Independent estimates'],
  ['history', 'Monthly record'],
];

function stepTab(current, key) {
  const order = TABS.map(([id]) => id);
  if (key === 'Home') return order[0];
  if (key === 'End') return order[order.length - 1];
  const at = order.indexOf(current);
  const next = key === 'ArrowLeft' ? at - 1 : at + 1;
  return order[(next + order.length) % order.length];
}

const json = url => fetch(url).then(response => response.ok
  ? response.json()
  : Promise.reject(new Error(`${response.status} while loading ${url}`)));

function WatchZoom({ onZoom }) {
  useMapEvent('moveend', event => {
    const map = event.target;
    const center = map.getCenter();
    try { saveMapView(window.localStorage, [center.lat, center.lng], map.getZoom()); } catch { /* Storage may be disabled. */ }
  });
  useMapEvent('zoomend', event => onZoom(event.target.getZoom()));
  return null;
}

function FitTo({ bounds, resetVersion }) {
  const map = useMap();
  useEffect(() => {
    if (resetVersion === 0) return;
    map.setView(DEFAULT_MAP_VIEW.center, DEFAULT_MAP_VIEW.zoom, { animate: false });
    // A programmatic reset does not reliably reach the moveend listener, so the
    // next page load would restore the pre-reset view; store it explicitly.
    try { saveMapView(window.localStorage, DEFAULT_MAP_VIEW.center, DEFAULT_MAP_VIEW.zoom); } catch { /* Storage may be disabled. */ }
  }, [resetVersion, map]);
  useEffect(() => {
    const mobile = map.getSize().x <= 820;
    if (bounds) map.flyToBounds(bounds, {
      paddingTopLeft: mobile ? [16, 16] : OCCLUDED_TOP_LEFT,
      paddingBottomRight: mobile ? [36, 36] : OCCLUDED_BOTTOM_RIGHT,
      duration: 0.8,
      maxZoom: 14,
      animate: !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
    });
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
  const [tab, setTab] = useState('original');

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

      <div className="land-modal-tabs" role="tablist" aria-label="Basin attribute views">
        {TABS.map(([id, label]) => <button
          key={id} type="button" role="tab" id={`basin-tab-${id}`} aria-controls={`basin-panel-${id}`}
          aria-selected={tab === id} tabIndex={tab === id ? 0 : -1} onClick={() => setTab(id)}
          onKeyDown={event => { if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
            event.preventDefault(); const next = stepTab(tab, event.key);
            setTab(next); document.getElementById(`basin-tab-${next}`)?.focus();
          } }}>{label}</button>)}
      </div>
      {tab !== 'history' && <div className="land-modal-tools">
        <label><Search size={12}/><input value={filter} onChange={event => setFilter(event.target.value)}
          placeholder="Attribute, category or column"/></label>
        <div className="land-modal-kinds">
          {[['all', 'All'], ['basin_specific', 'This sub-basin'], ['basin_accumulation', 'Upstream']].map(([id, label]) =>
            <button key={id} type="button" className={kind === id ? 'active' : ''} onClick={() => setKind(id)}>{label}</button>)}
        </div>
        {tab === 'original' && <span>{formatNumber(rows.length)} attributes</span>}
      </div>}

      <div className="land-modal-scroll" role="tabpanel" id={`basin-panel-${tab}`} aria-labelledby={`basin-tab-${tab}`}>
        {tab === 'history' ? <BasinHistory key={`h-${basin.basin_level}-${basin.hybas_id}`} basin={basin}/>
          : tab === 'substitutes' ? <BasinSubstitutes key={`${basin.basin_level}-${basin.hybas_id}`} basin={basin} filter={filter} kind={kind}/>
          : loading && !store ? <p className="land-group-note">Loading the atlas attributes…</p>
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
        {tab === 'original' && !rows.length && store ? <p className="land-group-note">Nothing matches that filter.</p> : null}
      </div>

      <footer>
        <span>Values join on <code>hybas_id</code>; river reaches inherit through <code>HYBAS_L12</code>.</span>
        <a href="/metadata.html">Full attribute catalogue <ArrowUpRight size={11}/></a>
      </footer>
    </section>
  </div>;
}

// Basemaps a reader can switch between. Satellite answers "what is actually on
// the ground there", terrain answers "why does the water go that way", and the
// plain option takes the basemap away so the basin colouring stands alone.
// Each carries the attribution its licence requires; dimming is applied only to
// the cartographic maps, because dimming imagery destroys what it is for.
const BASEMAPS = [
  {
    id: 'map', label: 'Street map',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19, dim: true,
  },
  {
    id: 'satellite', label: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
    maxZoom: 19, dim: false,
  },
  {
    id: 'terrain', label: 'Terrain',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Shaded relief &copy; Esri',
    maxZoom: 13, dim: true,
  },
  { id: 'none', label: 'No basemap', url: null, attribution: '', dim: false },
];

export default function LandingMap() {
  const theme = useTheme();
  const [initialView] = useState(() => {
    try { return readMapView(window.localStorage); } catch { return DEFAULT_MAP_VIEW; }
  });
  const [resetVersion, setResetVersion] = useState(0);
  const [basemap, setBasemap] = useState('map');
  const [ladder, setLadder] = useState(null);
  const [riverLadder, setRiverLadder] = useState(null);
  const [levels, setLevels] = useState({});
  const [riverTiers, setRiverTiers] = useState({});
  const [zoom, setZoom] = useState(initialView.zoom);
  const [groups, setGroups] = useState(null);
  const [storeRequested, setStoreRequested] = useState(false);
  const [loadingStore, setLoadingStore] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [peek, setPeek] = useState(false);
  const panelCloseTimer = useRef(null);
  const [stickyOpen, setStickyOpen] = useState(() => {
    try { return localStorage.getItem('uzgeodata-panel') === 'open'; } catch { return false; }
  });
  const panelOpen = stickyOpen || peek || !!selected;
  const setSticky = value => {
    setStickyOpen(value);
    try { localStorage.setItem('uzgeodata-panel', value ? 'open' : 'closed'); } catch { /* storage blocked */ }
  };
  // The header obeys the same contract as the reading panel: the map owns the
  // screen, a touch of the top edge or the brand tab summons the header, and a
  // click on the tab pins it open across visits.
  const [headPeek, setHeadPeek] = useState(false);
  const [headSticky, setHeadSticky] = useState(() => {
    try { return localStorage.getItem('uzgeodata-head') === 'open'; } catch { return false; }
  });
  const headOpen = headSticky || headPeek;
  const setHeadStickyValue = value => {
    setHeadSticky(value);
    try { localStorage.setItem('uzgeodata-head', value ? 'open' : 'closed'); } catch { /* storage blocked */ }
  };
  useEffect(() => {
    const onMove = event => {
      if (event.clientY <= 6) setHeadPeek(true);
      else if (event.clientY > 380) setHeadPeek(false);
    };
    document.addEventListener('mousemove', onMove, { passive: true });
    return () => document.removeEventListener('mousemove', onMove);
  }, []);
  const keepPanelOpen = useCallback(() => {
    if (panelCloseTimer.current !== null) window.clearTimeout(panelCloseTimer.current);
    panelCloseTimer.current = null;
    setPeek(true);
  }, []);
  const schedulePanelClose = useCallback(() => {
    if (panelCloseTimer.current !== null) window.clearTimeout(panelCloseTimer.current);
    panelCloseTimer.current = window.setTimeout(() => {
      panelCloseTimer.current = null;
      setPeek(false);
    }, PANEL_CLOSE_DELAY);
  }, []);
  // A touch of the left edge slides the panel out; leaving it lets it fall
  // closed again unless the reader pinned it. A short grace period lets the
  // pointer cross accordion gaps without dismissing the panel mid-navigation.
  useEffect(() => {
    const onMove = event => { if (event.clientX <= 6) keepPanelOpen(); };
    document.addEventListener('mousemove', onMove, { passive: true });
    return () => {
      document.removeEventListener('mousemove', onMove);
      if (panelCloseTimer.current !== null) window.clearTimeout(panelCloseTimer.current);
    };
  }, [keepPanelOpen]);
  useEffect(() => {
    const host = document.getElementById('uz-lang-host');
    if (host && !host.firstChild) mountSelect(host);
  }, []);
  const [hoveredId, setHoveredId] = useState(null);
  const [query, setQuery] = useState('');
  const [overlay, setOverlay] = useState('');
  // A reader who turns the colours down to read the base map under them usually
  // wants that again next visit; storage can be unavailable, so it is a nicety only.
  const [opacity, setOpacity] = useState(() => {
    try { return overlayOpacity(window.localStorage.getItem(OPACITY_KEY)); } catch { return OVERLAY_OPACITY.default; }
  });
  useEffect(() => {
    try { window.localStorage.setItem(OPACITY_KEY, String(opacity)); } catch { /* storage blocked */ }
  }, [opacity]);
  const [tableOpen, setTableOpen] = useState(false);
  // Area of interest. Drawing borrows map clicks, so basin selection is held off
  // through a ref the (stable) basin click handler can read.
  const [aoiDrawing, setAoiDrawing] = useState(false);
  const [aoiVertices, setAoiVertices] = useState([]);
  const [aoiClosed, setAoiClosed] = useState(false);
  const [aoiRule, setAoiRule] = useState('intersects');
  const drawingRef = useRef(false);
  useEffect(() => { drawingRef.current = aoiDrawing; }, [aoiDrawing]);
  const [catalogue, setCatalogue] = useState(null);
  const [bounds, setBounds] = useState(null);
  const [dams, setDams] = useState(null);
  const [showDams, setShowDams] = useState(false);
  const [dam, setDam] = useState(null);
  const [lakes, setLakes] = useState(null);
  const [showLakes, setShowLakes] = useState(false);
  const [lake, setLake] = useState(null);
  const [stations, setStations] = useState(null);
  const [showStations, setShowStations] = useState(false);
  const [station, setStation] = useState(null);
  // SVG only intercepts events on its interactive paths. A marker-pane canvas
  // covers the entire map and prevents the basin canvas underneath receiving clicks.
  const damRenderer = useMemo(() => svg({ pane: 'markerPane' }), []);
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
  useEffect(()=>{
    if(!showLakes||lakes)return;
    let live=true;
    json('/data/hydroclimate/water-bodies-reviewed.geojson').then(d=>{if(live)setLakes(d);}).catch(()=>{if(live)setShowLakes(false);});
    return()=>{live=false;};
  },[showLakes,lakes]);
  // Stations are off by default: they are evidence about the products rather than
  // part of the hydrography, and combined meteorological stations and discharge gauges
  // is a lot to impose on a reader who came to look at catchments.
  useEffect(()=>{
    if(!showStations||stations)return;
    let live=true;
    Promise.all([
      json('/data/hydroclimate/meteo-stations.geojson'),
      json('/data/research/ca-discharge-stations.geojson')
    ]).then(([meteo, gauges]) => {
      if(!live)return;
      // Merge both layers into one GeoJSON FeatureCollection
      const merged = {
        type: 'FeatureCollection',
        features: [
          ...meteo.features.map(f => ({...f, properties: {...f.properties, station_type: 'meteo'}})),
          ...gauges.features.map(f => ({...f, properties: {...f.properties, station_type: 'gauge'}}})
        ]
      };
      setStations(merged);
    }).catch(()=>{if(live)setShowStations(false);});
    return()=>{live=false;};
  },[showStations,stations]);
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
    if (!overlay || !store) return basinStyle(properties, state, opacity);
    return overlayStyle(properties, state, readAttribute(store, properties.hybas_id, overlay), overlayBreaks,
      undefined, opacity);
  }, [overlay, store, overlayBreaks, opacity]);

  // The area of interest always selects level-12 basins, whatever level is drawn,
  // so their geometry is fetched once an area is closed.
  const level12Entry = ladder?.levels?.find(entry => entry.level === 12);
  useEffect(() => {
    if (!aoiClosed || !level12Entry || levels[12]) return undefined;
    let live = true;
    json(level12Entry.url)
      .then(document => live && setLevels(current => ({ ...current, 12: document })))
      .catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, [aoiClosed, level12Entry, levels]);
  const aoiSelection = useMemo(() => (aoiClosed && levels[12]
    ? selectBasins(levels[12].features, aoiVertices, aoiRule) : []), [aoiClosed, levels, aoiVertices, aoiRule]);
  // Vertices are mirrored in a ref as they are added: a double-click's own clicks
  // may not have rendered by the time the double-click asks to finish.
  const aoiVerticesRef = useRef(aoiVertices);
  aoiVerticesRef.current = aoiVertices;
  const addAoiVertex = useCallback(vertex => {
    const current = aoiVerticesRef.current;
    const last = current[current.length - 1];
    if (last && last[0] === vertex[0] && last[1] === vertex[1]) return;
    aoiVerticesRef.current = [...current, vertex];
    setAoiVertices(aoiVerticesRef.current);
  }, []);
  const finishAoi = useCallback(() => {
    if (aoiVerticesRef.current.length < 3) return;
    setAoiDrawing(false);
    setAoiClosed(true);
  }, []);
  const startAoi = useCallback(() => { aoiVerticesRef.current = []; setAoiVertices([]); setAoiClosed(false); setAoiDrawing(true); }, []);
  const clearAoi = useCallback(() => { aoiVerticesRef.current = []; setAoiVertices([]); setAoiClosed(false); setAoiDrawing(false); }, []);

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
      click: () => {
        if (drawingRef.current) return; setSelected(feature); setDam(null); setLake(null); setStation(null); setQuery(''); setStoreRequested(true); setTableOpen(true); },
    });
  }, []);

  const focus = feature => {
    setSelected(feature);
    setDam(null);
    setLake(null);
    setQuery('');
    setBounds(featureBounds(feature));
  };

  const focusSystem = system => {
    const members = features.filter(feature => feature.properties.system_id === system);
    if (members.length) setBounds(collectionBounds(members));
  };

  const base = BASEMAPS.find(entry => entry.id === basemap) || BASEMAPS[0];

  if (error) return <main className="land-state"><h1>The map could not load.</h1><p>{error}</p>
    <button type="button" onClick={() => window.location.reload()}>Try again</button>
    <p><a href="/guide.html">Get help or download basin data directly</a></p></main>;

  return <>
    <main className="land">
    <MapContainer center={initialView.center} zoom={initialView.zoom} minZoom={0} maxZoom={19} zoomControl={false} className="land-map" preferCanvas>
      {base.url && <TileLayer attribution={base.attribution} key={`${base.id}-${theme}`}
        url={base.url} maxZoom={base.maxZoom}
        className={base.dim ? 'land-tiles-dim' : 'land-tiles-plain'}
        opacity={base.dim ? (theme === 'light' ? 0.78 : 0.5) : 1}/>}
      {/* smoothFactor 0: Leaflet simplifies each polygon on its own, which pulls
          neighbouring borders apart; the geometry is already simplified as a coverage. */}
      {basins && <GeoJSON key={active.level} data={basins} smoothFactor={0}
        style={feature => styleFor(feature.properties, {})} onEachFeature={onEachFeature}/>}
      {rivers && <GeoJSON key={`rivers-${tier.id}`} data={rivers} style={feature => riverStyle(feature.properties)}
        interactive={false} smoothFactor={1.2}/>}
      {showLakes&&lakes&&<LakeLayer data={lakes} onSelect={properties=>{setLake(properties);setDam(null);setStation(null);setTableOpen(false);}}/>}
      {showStations&&stations&&<StationLayer data={stations} onSelect={properties=>{setStation(properties);setLake(null);setDam(null);setTableOpen(false);}}/>}
      {/* SVG markers remain above basins while allowing clicks between symbols
          to reach the basin canvas, including after a basin-level remount. */}
      {damClusters.map(cluster => {
        if (cluster.count === 1) {
          const feature = cluster.members[0];
          const state = { selected: dam?.dam_id === feature.properties.dam_id };
          return <CircleMarker key={`dam-${feature.properties.dam_id}`} pane="markerPane" renderer={damRenderer}
            center={[cluster.latitude, cluster.longitude]}
            pathOptions={damStyle(feature.properties, state)}
            radius={damStyle(feature.properties, state).radius}
            eventHandlers={{ click: () => { setDam(feature.properties); setLake(null); setStation(null); setSelected(null); setTableOpen(false); } }}>
            <Tooltip direction="top" offset={[0, -4]} opacity={1} className="land-dam-tip">
              {damLabel(feature.properties)}
            </Tooltip>
          </CircleMarker>;
        }
        return <CircleMarker key={`group-${cluster.key}`} pane="markerPane" renderer={damRenderer}
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
      <AoiLayer drawing={aoiDrawing} vertices={aoiVertices} closed={aoiClosed} selection={aoiSelection}
        onAdd={addAoiVertex} onFinish={finishAoi} onCancel={clearAoi}/>
      <FitTo bounds={bounds} resetVersion={resetVersion}/>
      <WatchZoom onZoom={setZoom}/>
      <ZoomControl position="bottomright"/>
      <ScaleControl position="bottomright" imperial={false}/>
    </MapContainer>

    <header className={`land-head ${headOpen ? '' : 'uz-closed'}`}>
      <div className="land-head-top">
        <div>
          <a href="/" className="land-brand" aria-label="UzGeoData home">
            <span className="land-brand-icon" aria-hidden="true">&#8776;</span>
            <span className="land-brand-word">UZGEODATA</span>
            <span className="land-brand-sub">BASIN ATLAS</span>
          </a>
          <h1>Where the water forms</h1>
        </div>
        <div className="land-head-tools">
          <a className="land-project-link" href="/project.html">Project overview <ArrowUpRight size={12}/></a>
          <button className="land-view-button" type="button" onClick={() => {
            setBounds(null); setResetVersion(value => value + 1);
          }} title="Return to the starting map location and zoom">Reset view</button>
          <ThemeToggle className="land-theme"/>
        </div>
      </div>
      <p>Amu Darya and Syr Darya as they drain, not as borders cut them. Pick any sub-basin to read it.</p>
    </header>

    <section className="land-mapctrl" aria-label="Map display controls">
      <label className="land-basemap">
            <span>Basemap</span>
            <select value={basemap} onChange={event => setBasemap(event.target.value)}
              aria-label="Basemap">
              {BASEMAPS.map(entry => <option key={entry.id} value={entry.id}>{entry.label}</option>)}
            </select>
          </label>
      {/* Water bodies and barriers are map layers, so they are switched on
              the map rather than from a reading panel down the side. */}
          <fieldset className="land-layers">
            <legend>Layers</legend>
            <label className="land-toggle">
              <input type="checkbox" checked={showLakes} onChange={event => {
                setShowLakes(event.target.checked);
                if (!event.target.checked) setLake(null);
              }}/>
              <span className="land-lake-key" aria-hidden="true"><i/><i/><i/></span>
              <span>Lakes{lakes ? ` · ${formatNumber(lakes.features.length)}` : ''}</span>
            </label>
            <label className="land-toggle">
              <input type="checkbox" checked={showDams} onChange={event => {
                setShowDams(event.target.checked);
                if (!event.target.checked) setDam(null);
              }}/>
              <Droplets size={12}/>
              <span>Dams{damStats ? ` · ${formatNumber(damStats.dams)}` : ''}</span>
            </label>
            <label className="land-toggle">
              <input type="checkbox" checked={showStations} onChange={event => {
                setShowStations(event.target.checked);
                if (!event.target.checked) setStation(null);
              }}/>
              <span className="land-station-key" aria-hidden="true"/>
              <span>Observations{stations ? ` · ${formatNumber(stations.features.length)} stations & gauges` : ''}</span>
            </label>
          </fieldset>
      <span id="uz-lang-host" className="land-lang"/>
    </section>
    <button type="button" className="land-head-tab" aria-label="Toggle map header"
      aria-expanded={headOpen}
      onClick={() => setHeadStickyValue(!headSticky)}
      onMouseEnter={() => setHeadPeek(true)}>
      <span aria-hidden="true">&#8776;</span>
      <span className="uz-chev" aria-hidden="true">&#9662;</span>
    </button>

    <aside onMouseEnter={keepPanelOpen} onMouseLeave={schedulePanelClose}
      onFocusCapture={keepPanelOpen}
      onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget)) schedulePanelClose(); }}
      className={`land-panel ${selected ? 'has-selection' : ''} ${panelOpen ? '' : 'uz-closed'}`}>
      {!basins && <p className="land-loading">Loading the reference basins…</p>}
      {basins && <p className="land-level">
        Level {active.level} · {formatNumber(features.length)} basins
        {rivers ? ` · ${formatNumber(rivers.features.length)} reaches` : ''}
        {selected && Number(selected.properties.basin_level) !== active.level
          ? ` · selection held at level ${selected.properties.basin_level}` : ''}
      </p>}
      {basins && !selected && <div className="land-intro">
        <label className="land-search">
          <Search size={13}/>
          <input aria-label="Search basins by HYBAS or PFAF identifier" value={query} onChange={event => setQuery(event.target.value)} placeholder="HYBAS or PFAF id"/>
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
        <details className="land-group land-howto">
          <summary>Explore a basin in five minutes</summary>
          <div className="land-group-body">
            <p>Zoom in to level 12, select a basin, then open Atlas attributes to compare
              estimates and download its monthly record. <a href="/guide.html">Step-by-step guide</a></p>
          </div>
        </details>
      </div>}

      {selected && <div className="land-detail" style={{ '--system': systemMeta(selected.properties.system_id).color }}>
        <button type="button" className="land-close" onClick={() => setSelected(null)} aria-label="Clear selection"><X size={14}/></button>
        <span className="land-kicker">{systemMeta(selected.properties.system_id).label} · level {selected.properties.basin_level}</span>
        <h2>HYBAS {selected.properties.hybas_id}</h2>
        <button type="button" className="land-view-button" onClick={() => setBounds(featureBounds(selected))}>Zoom to selected basin</button>
        <dl className="land-headline">{basinHeadline(selected.properties).map(row => <div key={row.label}>
          <dt>{row.label}</dt>
          <dd>{row.value}{row.unit ? <em> {row.unit}</em> : null}</dd>
        </div>)}</dl>
        <button type="button" className="land-open-table" onClick={() => { setStoreRequested(true); setTableOpen(true); }}>
          <span>
            <strong>Atlas attributes</strong>
            <small>{groups?.groups?.reduce((total, group) => total + group.attributeCount, 0) || 281} published attributes, estimates and monthly downloads</small>
          </span>
          <ArrowUpRight size={13}/>
        </button>
        <p className="land-note">Upstream values already account for everything above this basin. They cannot be added together across basins.</p>
      </div>}

      <nav className="land-deeper">
        <details className="land-group">
          <summary><Layers size={12}/> Research &amp; case studies</summary>
          {DEEPER.map(item => <a key={item.href} href={item.href}>
            <span><strong>{item.label}</strong><small>{item.note}</small></span>
            <ArrowUpRight size={13}/>
          </a>)}
        </details>
        <details className="land-group">
          <summary><BookOpen size={12}/> About the project</summary>
          {PROGRAMME.map(item => <a key={item.id} href={item.href}>
            <span><strong>{item.label}</strong><small>{item.note}</small></span>
            <ArrowUpRight size={13}/>
          </a>)}
          <a href="/admin.html"><span><strong>Data freshness</strong><small>Variable inventory & update status</small></span><ArrowUpRight size={13}/></a>
        </details>
        <p className="land-hint">Public preview · Independent estimates; reproduction has not been established.</p>
      </nav>
    </aside>
    <button type="button" className="land-panel-tab" aria-label="Toggle basins panel"
      aria-expanded={panelOpen}
      onClick={() => setSticky(!panelOpen)}
      onMouseEnter={keepPanelOpen}
      onMouseLeave={schedulePanelClose}>
      <span aria-hidden="true">{panelOpen ? '\u2039' : '\u203a'}</span>
    </button>


    {basins && groups && <section className="land-dock" aria-label="Area of interest, basin colouring and map key">
      <AoiPanel drawing={aoiDrawing} vertices={aoiVertices} closed={aoiClosed} rule={aoiRule}
        selection={aoiSelection} loadingGeometry={aoiClosed && !levels[12]}
        onFit={() => setBounds(collectionBounds(aoiSelection.map(basin => basin.feature)))}
        onStart={startAoi} onFinish={finishAoi} onCancel={clearAoi} onClear={clearAoi} onRule={setAoiRule}/>
      <label className="land-dock-select">
        <span>Colour basins by</span>
        <select value={overlay} onChange={event => setOverlay(event.target.value)}>
          <option value="">River system</option>
          {HEADLINE_ATTRIBUTES.map(column => {
            const meta = attributeMeta(groups, column);
            return meta ? <option key={column} value={column}>{meta.label}</option> : null;
          })}
        </select>
      </label>
      <label className="land-opacity">
        <span>Basin colour opacity <output>{Math.round(opacity * 100)}%</output></span>
        <input type="range" min={OVERLAY_OPACITY.min} max={OVERLAY_OPACITY.max} step="0.02" value={opacity}
          aria-label="Basin colour opacity" onChange={event => setOpacity(overlayOpacity(event.target.value))}/>
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
      {!overlay && <p className="land-group-note">Basins are coloured by river system. Choose a measured
        attribute to shade them by value.</p>}
      {showDams && damStats && <div className="land-dock-key">
        <span>Storage, MCM</span>
        <ul className="land-sizekey">
          {damLegendStops().map(stop => <li key={stop.capacity}>
            <i style={{ width: stop.radius * 2, height: stop.radius * 2 }}/>
            <em>{formatNumber(stop.capacity)}</em>
          </li>)}
        </ul>
        <p className="land-group-note">{formatNumber(damStats.storageMcm)} MCM across {damStats.dams} barriers.
          A hollow ring is a barrier whose capacity the source never reported.</p>
      </div>}
    </section>}

    {tableOpen && selected && <AttributeModal basin={selected.properties} groups={groups} store={detailStore}
      catalogue={catalogue} loading={loadingStore} onClose={() => setTableOpen(false)}/>}

    {dam && <DamModal dam={dam} onClose={() => setDam(null)}/>}
    {lake && <LakeModal lake={lake} onClose={()=>setLake(null)}/>}
    {station && <StationModal station={station} onClose={()=>setStation(null)}/>}
    </main>

    <footer className="site-footer land-site-footer">
      <div>
        <a className="land-brand" href="/" aria-label="UzGeoData home">
          <span className="land-brand-icon" aria-hidden="true">&#8776;</span>
          <span className="land-brand-word">UZGEODATA</span>
          <span className="land-brand-sub">BASIN ATLAS</span>
        </a>
        <p>Water systems cross borders.<br/>Understanding them should, too.</p>
      </div>
      <div><strong>Explore</strong><a href="/">Basin explorer</a><a href="/examples.html">Practical examples</a><a href="/case-studies.html">Research case studies</a></div>
      <div><strong>Understand</strong><a href="/research.html">Research foundations</a><a href="/about.html#citation">Citation &amp; reuse</a><a href="/guide.html">Guide &amp; data access</a><a href="/roadmap.html">Research roadmap</a></div>
      <div><strong>Contribute</strong><a href="https://github.com/tim7en/uzgeodata">Project on GitHub &#8599;</a><a href="https://github.com/tim7en/uzgeodata/issues">Report an issue &#8599;</a><a href="/release.json">Release metadata</a></div>
      <p className="footer-note">Independent research project &middot; Public preview &middot; Amu Darya &amp; Syr Darya</p>
    </footer>
    </>;
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

function featureBounds(feature) {
  return collectionBounds([feature]);
}

export { SYSTEMS };
