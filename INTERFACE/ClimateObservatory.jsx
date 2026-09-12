import React, { useEffect, useMemo, useState } from 'react';
import { GeoJSON, MapContainer, ScaleControl, TileLayer, ZoomControl, useMap } from 'react-leaflet';
import L from 'leaflet';
import {
  ArrowUpRight, BarChart3, Braces, ChevronLeft, ChevronRight, Database, Layers,
  MapPin, Pause, Play, Search, Sparkles, Table2,
} from 'lucide-react';
import {
  cellAt, divergingColor, formatPeriod, frameTitle, periodLabel, periodValues, scopeLabel,
  sequentialColor, summaryStats, timelineFor, unitLabel, valueAt,
} from './basinLayersModel.js';

const INDEX_URL = '/data/basin-layers/index.json';
const NO_DATA = '#111a1f';
const SELECTED = '#ffffff';
const PREFERRED_VARIABLES = ['precipitation', 'precipitation_total', 'temperature_mean',
  'tmax_mean', 'ghm_mean', 'aod_550nm'];

function number(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return '\u2014';
  return Number(value).toLocaleString('en-US', {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  });
}

function featureId(feature, layer) {
  return String(feature?.properties?.[layer?.geometryIdColumn || 'HYBAS_ID'] ?? '');
}

function Logo() {
  return <a className="clim-logo" href="/" aria-label="UzGeoData home">
    <svg viewBox="0 0 38 38" aria-hidden="true"><path d="M5 7h8v15c0 5 2 8 6 8s6-3 6-8V7h8v16c0 9-5 14-14 14S5 32 5 23V7Z"/><path className="clim-logo-bar" d="M13 2h21v5H13z"/></svg>
    <span>UZ<span>GEO</span>DATA</span>
  </a>;
}

function MapFocus({ feature }) {
  const map = useMap();
  useEffect(() => {
    if (feature) map.flyToBounds(L.geoJSON(feature).getBounds(), {
      paddingTopLeft: [360, 90], paddingBottomRight: [390, 120], maxZoom: 10, duration: 0.75,
    });
  }, [feature, map]);
  return null;
}

function MiniLine({ points, color }) {
  const valid = points.filter(point => point.v !== null);
  if (valid.length < 2) return <div className="clim-chart-empty">More observations are needed for a trend.</div>;
  const width = 330; const height = 116; const pad = 13;
  const min = Math.min(...valid.map(point => point.v));
  const max = Math.max(...valid.map(point => point.v));
  const spread = Math.max(max - min, 1e-6);
  const x = point => pad + (points.indexOf(point) / Math.max(points.length - 1, 1)) * (width - pad * 2);
  const y = value => height - pad - ((value - min) / spread) * (height - pad * 2);
  const path = valid.map((point, index) => `${index ? 'L' : 'M'}${x(point)},${y(point.v)}`).join(' ');
  const area = `${path} L${x(valid.at(-1))},${height - pad} L${x(valid[0])},${height - pad} Z`;
  return <svg className="clim-mini-line" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Value over time">
    <defs><linearGradient id="clim-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".32"/><stop offset="1" stopColor={color} stopOpacity="0"/></linearGradient></defs>
    <path d={area} fill="url(#clim-area)"/>
    <path d={path} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke"/>
    {valid.map(point => <circle key={point.period} cx={x(point)} cy={y(point.v)} r="2.6" fill={color}/>)}
    <text x={pad} y="10">{number(max, 1)}</text><text x={pad} y={height - 1}>{number(min, 1)}</text>
  </svg>;
}

function Histogram({ values, min, max, color, bins = 10 }) {
  const model = useMemo(() => {
    if (!values.length) return [];
    const spread = Math.max(max - min, 1e-6);
    const width = spread / bins;
    const counts = Array.from({ length: bins }, () => 0);
    values.forEach(value => {
      const index = Math.min(bins - 1, Math.max(0, Math.floor((value - min) / width)));
      counts[index] += 1;
    });
    const peak = Math.max(...counts, 1);
    return counts.map((count, index) => ({ from: min + index * width, count, peak }));
  }, [values, min, max, bins]);
  if (!model.length) return <div className="clim-chart-empty">No spatial distribution for this period.</div>;
  return <div className="clim-histogram">
    {model.map(bin => <div key={bin.from}>
      <i style={{ height: `${Math.max(bin.count / bin.peak * 100, 2)}%`, background: color }}/>
      <span>{number(bin.from, 0)}</span>
    </div>)}
  </div>;
}

export default function ClimateObservatory() {
  const [index, setIndex] = useState(null);
  const [layerId, setLayerId] = useState(null);
  const [seriesCache, setSeriesCache] = useState({});
  const [geometryCache, setGeometryCache] = useState({});
  const [variable, setVariable] = useState(null);
  const [expression, setExpression] = useState('signal');
  const [periodIndex, setPeriodIndex] = useState(0);
  const [selectedId, setSelectedId] = useState(null);
  const [hoverId, setHoverId] = useState(null);
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState('insight');
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    fetch(INDEX_URL).then(response => {
      if (!response.ok) throw new Error(`${response.status} loading ${INDEX_URL}`);
      return response.json();
    }).then(data => {
      if (!live) return;
      setIndex(data);
      setLayerId(data.layers[0].id);
    }).catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, []);

  const layer = useMemo(() => index?.layers.find(item => item.id === layerId) || null, [index, layerId]);

  useEffect(() => {
    if (!layer) return;
    const preferred = PREFERRED_VARIABLES.find(code => layer.variables.some(v => v.code === code));
    setVariable(current => layer.variables.some(v => v.code === current)
      ? current : (preferred || layer.variables[0].code));
    setExpression(layer.kind === 'anomaly' ? 'signal' : 'value');
    setPeriodIndex(layer.periods.length - 1);
    setSelectedId(null);
    setPlaying(false);
  }, [layer]);

  useEffect(() => {
    if (!layer || seriesCache[layer.id]) return;
    let live = true;
    fetch(layer.series).then(r => r.json()).then(data => {
      if (live) setSeriesCache(current => ({ ...current, [layer.id]: data }));
    }).catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, [layer, seriesCache]);

  useEffect(() => {
    if (!layer || geometryCache[layer.geometry]) return;
    let live = true;
    fetch(layer.geometry).then(r => r.json()).then(data => {
      if (live) setGeometryCache(current => ({ ...current, [layer.geometry]: data }));
    }).catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, [layer, geometryCache]);

  useEffect(() => {
    if (!playing || !layer?.periods.length) return undefined;
    const timer = setInterval(() => setPeriodIndex(current => (current + 1) % layer.periods.length), 900);
    return () => clearInterval(timer);
  }, [playing, layer]);

  const series = layer ? seriesCache[layer.id] : null;
  const geometry = layer ? geometryCache[layer.geometry] : null;
  const period = layer?.periods[periodIndex];
  const activeVariable = useMemo(
    () => layer?.variables.find(v => v.code === variable) || layer?.variables[0],
    [layer, variable],
  );

  const observed = useMemo(
    () => series && period && variable ? periodValues(series, period, variable) : [],
    [series, period, variable],
  );
  const stats = useMemo(() => summaryStats(observed.map(item => item.v)), [observed]);
  const maxAbsZ = useMemo(() => {
    const zs = observed.map(item => Math.abs(item.z ?? 0));
    return Math.max(...zs, 1.5);
  }, [observed]);

  const signalMode = layer?.kind === 'anomaly' && expression === 'signal';

  const featureColor = id => {
    if (!series || !variable) return NO_DATA;
    const cell = cellAt(series, id, period, variable);
    if (!cell) return NO_DATA;
    if (signalMode) return divergingColor(cell.z ?? null, maxAbsZ) || NO_DATA;
    return sequentialColor(cell.v, stats.min ?? 0, stats.max ?? 1, activeVariable?.color || '#4cc9f0') || NO_DATA;
  };

  const visibleId = hoverId || selectedId;
  const visibleCell = visibleId && series && period && variable ? cellAt(series, visibleId, period, variable) : null;
  const visibleFeature = useMemo(() => geometry?.features.find(
    feature => featureId(feature, layer) === visibleId,
  ), [geometry, visibleId, layer]);
  const selectedFeature = useMemo(() => geometry?.features.find(
    feature => featureId(feature, layer) === selectedId,
  ), [geometry, selectedId, layer]);
  const timeline = useMemo(
    () => series && visibleId && layer ? timelineFor(series, visibleId, layer.periods, variable) : [],
    [series, visibleId, layer, variable],
  );

  const searchMatches = useMemo(() => {
    const term = query.trim();
    if (!term || !geometry) return [];
    return geometry.features.filter(feature =>
      featureId(feature, layer).includes(term)
      || String(feature.properties.PFAF_ID || '').includes(term)
    ).slice(0, 7);
  }, [query, geometry, layer]);

  const domains = useMemo(() => {
    if (!index) return [];
    const groups = new Map();
    index.layers.forEach(item => {
      const group = `${item.legacyScope ? 'NATIONAL ARCHIVE' : 'TRANSBOUNDARY'} / ${item.domain}`;
      if (!groups.has(group)) groups.set(group, []);
      groups.get(group).push(item);
    });
    return [...groups.entries()];
  }, [index]);

  const step = delta => layer && setPeriodIndex(current =>
    Math.min(layer.periods.length - 1, Math.max(0, current + delta)));

  if (error) return <div className="clim-fatal"><Sparkles/><h1>The observatory is waiting for data.</h1><p>{error}</p><code>npm run climate:web</code><a href="/">Return to portal</a></div>;
  if (!index || !layer || !series || !geometry || !period) return <div className="clim-loading"><span/><p>Assembling the basin observatory</p></div>;

  return <div className="clim-app">
    <section className="clim-stage">
      <MapContainer center={[41.25, 64.4]} zoom={5} minZoom={4} maxZoom={12} zoomControl={false} preferCanvas>
        <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
        <ZoomControl position="bottomleft"/><ScaleControl position="bottomright"/>
        <GeoJSON
          key={`${layer.id}-${period}-${variable}-${expression}-${selectedId}`}
          data={geometry}
          smoothFactor={0}
          style={feature => {
            const id = featureId(feature, layer);
            const selectedNow = id === selectedId;
            const color = featureColor(id);
            return {
              color: selectedNow ? SELECTED : color,
              weight: selectedNow ? 2 : .45,
              fillColor: color,
              fillOpacity: cellAt(series, id, period, variable) ? .82 : .18,
              opacity: selectedNow ? 1 : .6,
            };
          }}
          onEachFeature={(feature, leafletLayer) => {
            const id = featureId(feature, layer);
            leafletLayer.on({
              mouseover: () => setHoverId(id), mouseout: () => setHoverId(null),
              click: () => setSelectedId(id),
            });
          }}
        />
        <MapFocus feature={selectedFeature}/>
      </MapContainer>

      <header className="clim-header">
        <Logo/>
        <div className="clim-title"><span>ONTOLOGY APPLICATION / 02</span><strong>Basin climate & land observatory</strong></div>
        <nav><a href="/">Portal</a><a href="/case-studies.html">Case studies</a><a href="/ontology.html">Living ontology</a><a href="/landcover.html">Land cover</a><a href="/hydrography.html">Hydrography</a><a href="/relationships.html">Tables</a><a href="/catalogue.html">Catalogue</a></nav>
      </header>

      <aside className="clim-lens">
        <div className="clim-eyebrow"><Layers size={13}/> ANALYTICAL LENS <small>{formatPeriod(layer.periodGrain, period)}</small></div>
        <h1>See what's <em>changing.</em></h1>
        <p>{layer.what}</p>
        <div className="clim-search">
          <Search size={14}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Find basin or formation-system ID"/>
          {!!searchMatches.length && <div>{searchMatches.map(feature => {
            const id = featureId(feature, layer);
            return <button key={id} onClick={() => { setSelectedId(id); setQuery(''); }}><span>{feature.properties.label || `Basin ${feature.properties.PFAF_ID || id}`}</span><small>{id}</small></button>;
          })}</div>}
        </div>
        <label>Signal source</label>
        {domains.map(([domain, items]) => <div className="clim-domain-group" key={domain}>
          <span>{domain}</span>
          <div className="clim-layers">{items.map(item => <button key={item.id} className={item.id === layerId ? 'active' : ''}
            onClick={() => setLayerId(item.id)}><strong>{item.label}</strong><small>{unitLabel(item)} · {periodLabel(item)}</small><em>{scopeLabel(item.spatialScope)}</em></button>)}</div>
        </div>)}
        <label>Variable</label>
        <div className="clim-vars">
          {layer.variables.map(item => <button key={item.code} className={item.code === variable ? 'active' : ''}
            style={{ '--var-color': item.color }} onClick={() => setVariable(item.code)}><i/>{item.label}</button>)}
        </div>
        {layer.kind === 'anomaly' && <>
          <label>Map expression</label>
          <div className="clim-modes">
            <button className={expression === 'signal' ? 'active' : ''} onClick={() => setExpression('signal')}>Anomaly (z)</button>
            <button className={expression === 'value' ? 'active' : ''} onClick={() => setExpression('value')}>Raw value</button>
          </div>
        </>}
        <div className="clim-ontology-path"><span>ONTOLOGY PATH</span><code>{layer.dataset}</code><b>{layer.predicate}</b><code>{layer.spatialScope} / {layer.spatialUnit}</code></div>
      </aside>

      <aside className="clim-insight">
        <div className="clim-insight-tabs">
          {[['insight', BarChart3, 'Insight'], ['table', Table2, 'Table'], ['json', Braces, 'JSON']].map(([key, Icon, label]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}><Icon size={12}/>{label}</button>)}
        </div>
        {tab === 'insight' && <div className="clim-insight-body">
          <div className="clim-feature-id"><MapPin size={13}/><span>{visibleId ? `${layer.geometryIdColumn === 'HYBAS_ID' ? 'HYBAS ' : ''}${visibleId}` : 'ALL MEASURED UNITS'}</span></div>
          <h2>{visibleId ? (visibleFeature?.properties.label || `Basin ${visibleFeature?.properties.PFAF_ID ?? visibleId}`) : frameTitle(layer)}</h2>
          <div className="clim-big-number" style={{ color: activeVariable?.color }}>
            {visibleCell ? `${number(visibleCell.v, 2)} ${activeVariable?.unit || ''}` : (visibleId ? 'No observation' : number(stats.mean, 2))}
          </div>
          <span className="clim-big-caption">{activeVariable?.label} \u00b7 {formatPeriod(layer.periodGrain, period)}</span>
          {visibleCell?.c && <div className="clim-classification" style={{ color: divergingColor(visibleCell.z, maxAbsZ) || activeVariable?.color, borderColor: divergingColor(visibleCell.z, maxAbsZ) || 'var(--clim-line)' }}>{visibleCell.c}{visibleCell.z !== null && ` \u00b7 z ${visibleCell.z > 0 ? '+' : ''}${number(visibleCell.z, 2)}`}</div>}
          <div className="clim-mini-stats">
            <div><span>Observed units</span><strong>{number(observed.length, 0)}</strong></div>
            <div><span>Selection median</span><strong>{number(stats.median, 2)} {activeVariable?.unit || ''}</strong></div>
            <div><span>Selection min</span><strong>{number(stats.min, 2)}</strong></div>
            <div><span>Selection max</span><strong>{number(stats.max, 2)}</strong></div>
          </div>
          <div className="clim-chart-title"><span>TEMPORAL SIGNATURE</span><small>{formatPeriod(layer.periodGrain, layer.periods[0])}\u2014{formatPeriod(layer.periodGrain, layer.periods.at(-1))}</small></div>
          <MiniLine points={timeline} color={activeVariable?.color}/>
        </div>}
        {tab === 'table' && <div className="clim-table-wrap"><table><thead><tr><th>Period</th><th>Value</th><th>Z</th><th>Class</th></tr></thead><tbody>{timeline.map(point => <tr key={point.period}><td>{formatPeriod(layer.periodGrain, point.period)}</td><td>{number(point.v, 2)}</td><td>{point.z === null ? '\u2014' : number(point.z, 2)}</td><td>{point.c || '\u2014'}</td></tr>)}</tbody></table></div>}
        {tab === 'json' && <div className="clim-json"><div><span>LIVE GRAPH PROJECTION</span><a href={layer.series}>Open file <ArrowUpRight size={11}/></a></div><pre>{JSON.stringify({
          '@id': selectedId ? `uz:basin/${selectedId}` : null,
          '@type': 'Basin',
          predicate: layer.predicate,
          dataset: layer.dataset,
          variable,
          period,
          observation: visibleCell,
        }, null, 2)}</pre></div>}
      </aside>

      <div className="clim-map-readout">
        <div><span>MEASURED UNITS</span><strong>{number(observed.length, 0)}</strong></div>
        <div><span>SIGNAL</span><strong>{activeVariable?.label}</strong></div>
        <div><span>SPATIAL MEDIAN</span><strong>{number(stats.median, 2)} {activeVariable?.unit || ''}</strong></div>
      </div>

      <div className="clim-timeline">
        <button className="clim-play" onClick={() => setPlaying(current => !current)}>{playing ? <Pause size={14}/> : <Play size={14}/>}</button>
        <button className="clim-step" onClick={() => { setPlaying(false); step(-1); }} aria-label="Previous period"><ChevronLeft size={14}/></button>
        <div className="clim-scrub">
          <div className="clim-scrub-top"><strong>{formatPeriod(layer.periodGrain, period)}</strong><span>{periodIndex + 1} / {layer.periods.length}</span></div>
          <input type="range" min={0} max={layer.periods.length - 1} value={periodIndex}
            onChange={event => { setPlaying(false); setPeriodIndex(Number(event.target.value)); }}/>
        </div>
        <button className="clim-step" onClick={() => { setPlaying(false); step(1); }} aria-label="Next period"><ChevronRight size={14}/></button>
        <div className="clim-resolution"><span>LEVEL</span><strong>{layer.basinLevel}</strong><span>GRAIN</span><strong>{layer.periodGrain}</strong></div>
      </div>
    </section>

    <section className="clim-evidence">
      <div className="clim-evidence-intro"><span>THE PRACTICAL ANSWER</span><h2>Where is the signal moving \u2014 and by how much?</h2><p>Upstream layers are refreshed from Earth Engine and retain their native monthly or daily grain. Legacy national-intersection layers remain labelled for comparison. Pick a variable, scrub through time, then open the exact unit-period JSON behind the visual.</p></div>
      <div className="clim-distribution"><div className="clim-section-title"><BarChart3 size={14}/><span>SPATIAL DISTRIBUTION</span><small>{number(observed.length, 0)} observed units</small></div><Histogram values={observed.map(item => item.v)} min={stats.min ?? 0} max={stats.max ?? 1} color={activeVariable?.color}/><p>Distribution of {activeVariable?.label.toLowerCase()} across every measured unit in {formatPeriod(layer.periodGrain, period)}.</p></div>
      <div className="clim-national"><div className="clim-section-title"><Database size={14}/><span>SIGNAL LEGEND</span><small>{signalMode ? 'anomaly' : 'raw value'}</small></div>
        {signalMode ? <div className="clim-legend"><div className="clim-legend-bar" style={{ background: 'linear-gradient(90deg,#39a7ff,#263134,#ff695d)' }}/><div className="clim-legend-labels"><span>Below normal</span><span>Normal</span><span>Above normal</span></div></div>
          : <div className="clim-legend"><div className="clim-legend-bar" style={{ background: `linear-gradient(90deg,#172121,${activeVariable?.color})` }}/><div className="clim-legend-labels"><span>{number(stats.min, 1)}</span><span>{number(stats.max, 1)} {activeVariable?.unit}</span></div></div>}
      </div>
    </section>

    <section className="clim-provenance">
      <div><Sparkles size={22}/><span>MEASUREMENT, NOT INFERENCE</span></div>
      <p>{layer.what}</p>
      <div className="clim-provenance-grid"><span><small>DATASET</small>{layer.dataset}</span><span><small>PREDICATE</small>{layer.predicate}</span><span><small>REFERENCE</small>Basin level {layer.basinLevel}</span><span><small>COVERAGE</small>{layer.coverage.rows.toLocaleString()} rows \u00b7 {layer.coverage.basins.toLocaleString()} basins \u00b7 {layer.coverage.periods.toLocaleString()} periods</span></div>
    </section>
  </div>;
}
