import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CircleMarker, GeoJSON, MapContainer, ScaleControl, TileLayer, Tooltip, ZoomControl, useMapEvent } from 'react-leaflet';
import { ArrowLeft, BookOpen, Database, Droplets, Scale, Search, X } from 'lucide-react';
import {
  damHeadline, damLabel, damLegendStops, damStyle, damTotals,
  formatAttribute, formatNumber, indexStore, legendStops, levelForZoom, overlayStyle,
  quantileBreaks, readAttribute, riverStyle, systemMeta, tierForZoom,
} from './landingModel.js';

const LADDER_URL = '/data/hydroclimate/reference-basin-levels.json';
const RIVER_LADDER_URL = '/data/hydroclimate/reference-river-levels.json';
const GROUPS_URL = '/data/hydroclimate/reference-attribute-groups.json';
const CATALOGUE_URL = '/data/hydroclimate/reference-attribute-catalogue.json';
const DAMS_URL = '/data/hydroclimate/dams-transboundary.geojson';
const CENTRE = [40.2, 70.5];
const DEFAULT_ATTRIBUTE = 'dis_m3_pyr';
const GROUP_LABELS = { basin_specific: 'This sub-basin', basin_accumulation: 'Upstream catchment' };

const json = url => fetch(url).then(response => response.ok
  ? response.json()
  : Promise.reject(new Error(`${response.status} while loading ${url}`)));

function WatchZoom({ onZoom }) {
  useMapEvent('zoomend', event => onZoom(event.target.getZoom()));
  return null;
}

function attributeIndex(groups) {
  const list = [];
  for (const group of groups?.groups || []) {
    for (const category of group.categories) {
      for (const attribute of category.attributes) {
        list.push({ ...attribute, group: group.id, category: category.id });
      }
    }
  }
  return list;
}

export default function AtlasExplorer() {
  const [ladder, setLadder] = useState(null);
  const [riverLadder, setRiverLadder] = useState(null);
  const [groups, setGroups] = useState(null);
  const [catalogue, setCatalogue] = useState(null);
  const [levels, setLevels] = useState({});
  const [stores, setStores] = useState({});
  const [riverTiers, setRiverTiers] = useState({});
  const [zoom, setZoom] = useState(6);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [attribute, setAttribute] = useState(() => {
    const requested = new URLSearchParams(window.location.search).get('attribute');
    return requested || DEFAULT_ATTRIBUTE;
  });
  const [hit, setHit] = useState(null);
  const [dams, setDams] = useState(null);
  const [showDams, setShowDams] = useState(true);
  const [dam, setDam] = useState(null);

  useEffect(() => {
    let live = true;
    Promise.all([json(LADDER_URL), json(RIVER_LADDER_URL), json(GROUPS_URL), json(CATALOGUE_URL)])
      .then(([ladderDocument, riverDocument, groupDocument, catalogueDocument]) => {
        if (!live) return;
        setLadder(ladderDocument);
        setRiverLadder(riverDocument);
        setGroups(groupDocument);
        setCatalogue(catalogueDocument);
      })
      .catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, []);

  useEffect(() => {
    if (!showDams || dams) return undefined;
    let live = true;
    // The dam layer is an overlay, not the subject of this page: if it is missing
    // the atlas still has to draw, so its failure turns the toggle off rather
    // than replacing the map with an error.
    json(DAMS_URL).then(document => live && setDams(document)).catch(() => live && setShowDams(false));
    return () => { live = false; };
  }, [showDams, dams]);

  const damStats = useMemo(() => (dams ? damTotals(dams.features) : null), [dams]);

  const active = useMemo(() => levelForZoom(zoom, ladder), [zoom, ladder]);
  const basins = active ? levels[active.level] : null;
  const store = active ? stores[active.level] : null;
  const tier = useMemo(() => tierForZoom(zoom, riverLadder), [zoom, riverLadder]);
  const rivers = tier ? riverTiers[tier.id] : null;

  useEffect(() => {
    if (!active || levels[active.level]) return undefined;
    let live = true;
    json(active.url).then(document => live && setLevels(current => ({ ...current, [active.level]: document })))
      .catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, [active, levels]);

  useEffect(() => {
    if (!active || stores[active.level]) return undefined;
    let live = true;
    json(active.attributesUrl)
      .then(document => live && setStores(current => ({ ...current, [active.level]: indexStore(document) })))
      .catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, [active, stores]);

  useEffect(() => {
    if (!tier || riverTiers[tier.id]) return undefined;
    let live = true;
    json(tier.url).then(document => live && setRiverTiers(current => ({ ...current, [tier.id]: document })))
      .catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, [tier, riverTiers]);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set('attribute', attribute);
    window.history.replaceState({}, '', url);
  }, [attribute]);

  const attributes = useMemo(() => attributeIndex(groups), [groups]);
  const meta = attributes.find(entry => entry.column === attribute) || null;
  const variable = useMemo(() => {
    const code = catalogue?.columnIndex?.[attribute]?.variable;
    return catalogue?.variables?.find(entry => entry.code === code) || null;
  }, [catalogue, attribute]);

  const values = store?.values?.[attribute] || null;
  const breaks = useMemo(() => (values ? quantileBreaks(values) : []), [values]);
  const legend = useMemo(() => legendStops(breaks), [breaks]);
  const styleFor = useCallback(feature => overlayStyle(
    feature.properties, {}, readAttribute(store, feature.properties.hybas_id, attribute), breaks,
  ), [store, attribute, breaks]);

  const results = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return attributes.slice(0, 40);
    return attributes.filter(entry => entry.label.toLowerCase().includes(term)
      || entry.column.includes(term)).slice(0, 40);
  }, [query, attributes]);

  const onEachFeature = useCallback((feature, layer) => {
    layer.on({ click: () => setHit(feature.properties) });
  }, []);

  if (error) return <main className="atlas-state"><h1>The atlas could not load.</h1><p>{error}</p></main>;

  const reading = hit ? formatAttribute(readAttribute(store, hit.hybas_id, attribute), meta?.units) : null;

  return <main className="atlas">
    <aside className="atlas-rail">
      <a className="atlas-back" href="/"><ArrowLeft size={13}/> Map</a>
      <h1>Atlas explorer</h1>
      <p className="atlas-lede">Any of the {attributes.length} BasinATLAS attributes, drawn on the reference basins.</p>

      <label className="atlas-search">
        <Search size={13}/>
        <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Attribute or column"/>
      </label>
      <div className="atlas-list">
        {results.map(entry => <button key={entry.column} type="button"
          className={entry.column === attribute ? 'active' : ''} onClick={() => { setAttribute(entry.column); setHit(null); }}>
          <span><strong>{entry.label}</strong><small>{entry.category} · {GROUP_LABELS[entry.group]}</small></span>
          <code>{entry.column}</code>
        </button>)}
        {!results.length && <p className="atlas-dim">Nothing matches that.</p>}
      </div>

      <div className="atlas-dams">
        <label className="atlas-toggle">
          <input type="checkbox" checked={showDams} onChange={event => {
            setShowDams(event.target.checked);
            if (!event.target.checked) setDam(null);
          }}/>
          <Droplets size={12}/>
          <span>Dams and reservoirs</span>
        </label>
        {showDams && damStats && <>
          <p className="atlas-dim">
            {damStats.dams} barriers holding {formatNumber(damStats.storageMcm)} MCM,
            {' '}{damStats.inFormationZone} of them where the runoff forms.
          </p>
          <ul className="atlas-sizekey">
            {damLegendStops().map(stop => <li key={stop.capacity}>
              <i style={{ width: stop.radius * 2, height: stop.radius * 2 }}/>
              <em>{formatNumber(stop.capacity)}</em>
            </li>)}
          </ul>
          <p className="atlas-dim atlas-sizenote">
            Circle width follows storage on a logarithmic scale, in MCM — the range runs
            from 1 to 19,500, so equal areas would hide every dam but the largest.
            A hollow ring is a barrier whose capacity the source never reported.
          </p>
        </>}
        {showDams && !damStats && <p className="atlas-dim">Loading dams…</p>}
      </div>
    </aside>

    <section className="atlas-stage">
      <MapContainer center={CENTRE} zoom={6} zoomControl={false} className="atlas-map" preferCanvas>
        <TileLayer attribution="&copy; OpenStreetMap contributors"
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" opacity={0.42}/>
        {basins && store && <GeoJSON key={`${active.level}-${attribute}`} data={basins} smoothFactor={1.6}
          style={styleFor} onEachFeature={onEachFeature}/>}
        {rivers && <GeoJSON key={`rivers-${tier.id}`} data={rivers} interactive={false}
          style={feature => riverStyle(feature.properties)} smoothFactor={1.2}/>}
        {/* The dams go in the marker pane, not the overlay pane the basins use:
            Leaflet hands a canvas click to the layer added last, and the basin
            GeoJSON remounts on every level or attribute change, so sharing a
            renderer with it makes the dams stop responding at unpredictable
            moments. Their own pane settles both stacking and hit order. */}
        {showDams && dams?.features.map(feature => {
          const [longitude, latitude] = feature.geometry.coordinates;
          const selected = dam?.dam_id === feature.properties.dam_id;
          return <CircleMarker key={feature.properties.dam_id} center={[latitude, longitude]}
            pane="markerPane"
            pathOptions={damStyle(feature.properties, { selected })}
            radius={damStyle(feature.properties, { selected }).radius}
            eventHandlers={{ click: () => { setDam(feature.properties); setHit(null); } }}>
            <Tooltip direction="top" offset={[0, -4]} opacity={1} className="atlas-dam-tip">
              {damLabel(feature.properties)}
            </Tooltip>
          </CircleMarker>;
        })}
        <WatchZoom onZoom={setZoom}/>
        <ZoomControl position="bottomright"/>
        <ScaleControl position="bottomright" imperial={false}/>
      </MapContainer>

      <div className="atlas-legend">
        <span className="atlas-legend-title">{meta?.label || attribute}</span>
        <span className="atlas-legend-unit">{meta?.units || ''} · level {active?.level ?? '—'}</span>
        {!store && <p className="atlas-dim">Loading values…</p>}
        <ol>{legend.map((stop, index) => <li key={index}>
          <i style={{ background: stop.color }}/>
          <em>{stop.from === null ? `< ${formatAttribute(stop.to, meta?.units).value}`
            : stop.to === null ? `≥ ${formatAttribute(stop.from, meta?.units).value}`
              : `${formatAttribute(stop.from, meta?.units).value} – ${formatAttribute(stop.to, meta?.units).value}`}</em>
        </li>)}</ol>
        <p className="atlas-dim">Quantile classes over the basins in view. Basins without a measurement stay unfilled.</p>
      </div>

      {dam && <div className="atlas-dam-card">
        <button type="button" className="atlas-dam-close" onClick={() => setDam(null)} aria-label="Close">
          <X size={13}/>
        </button>
        <span className="atlas-kicker">{systemMeta(dam.system_id).label}</span>
        <h3>{damLabel(dam)}</h3>
        <dl>{damHeadline(dam).map(row => <div key={row.label}>
          <dt>{row.label}</dt><dd>{row.value} {row.unit && <em>{row.unit}</em>}</dd>
        </div>)}</dl>
        <p className="atlas-dim">
          {Number(dam.in_headwater_formation) === 1
            ? 'Stands in a runoff-formation zone: it regulates water where it is generated.'
            : 'Stands downstream of the formation zones, on water generated above it.'}
        </p>
        <p className="atlas-cite"><Database size={11}/>
          <span className="atlas-ids">
            <b>GDW <code>{dam.dam_id}</code></b>
            {dam.grand_id ? <b>GRanD <code>{dam.grand_id}</code></b> : null}
            {dam.hylak_id ? <b>HydroLAKES <code>{dam.hylak_id}</code></b> : null}
            {dam.hyriv_id ? <b>reach <code>{dam.hyriv_id}</code></b> : null}
            <b>basin <code>{dam.hybas_id_level12}</code></b>
          </span>
        </p>
        <p className="atlas-cite"><Scale size={11}/>
          Global Dam Watch v1.0, CC BY 4.0. Storage is nominal capacity, not an operating
          level{dam.position_source === 'snapped to the river network'
            ? '; this dam has no reported coordinate and is placed on the river centreline'
            : ''}.
        </p>
      </div>}

      {hit && !dam && <div className="atlas-hit">
        <strong>HYBAS {hit.hybas_id}</strong>
        <span>{systemMeta(hit.system_id).label} · level {hit.basin_level}</span>
        <b>{reading?.value} <em>{reading?.unit}</em></b>
      </div>}
    </section>

    <aside className="atlas-meta">
      <span className="atlas-kicker">{GROUP_LABELS[meta?.group] || ''}</span>
      <h2>{meta?.label || attribute}</h2>
      {variable ? <>
        <p>{variable.description}</p>
        <dl>
          <div><dt>Source product</dt><dd>{variable.source || '—'}</dd></div>
          <div><dt>Native resolution</dt><dd>{variable.nativeFormat || '—'}</dd></div>
          <div><dt>Measured over</dt><dd>{meta?.spatialExtentLabel || '—'}</dd></div>
          <div><dt>Dimension</dt><dd>{meta?.dimensionLabel || '—'}</dd></div>
        </dl>
        <p className="atlas-cite"><BookOpen size={11}/> {variable.citation}</p>
        <p className="atlas-cite"><Scale size={11}/> {variable.licence}</p>
        <p className="atlas-cite"><Database size={11}/> Joined to the reference basins on <code>hybas_id</code>; reaches inherit through <code>HYBAS_L12</code>.</p>
        <a className="atlas-more" href="/metadata.html">All {catalogue?.counts?.variables} variables in the catalogue</a>
      </> : <p className="atlas-dim">Loading the catalogue…</p>}
    </aside>
  </main>;
}
