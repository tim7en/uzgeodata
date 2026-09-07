import React, { useEffect, useMemo, useState } from 'react';
import { GeoJSON, MapContainer, ScaleControl, TileLayer, ZoomControl, useMap } from 'react-leaflet';
import L from 'leaflet';
import {
  ArrowUpRight, BarChart3, Braces, Database, Layers, MapPin, Pause, Play,
  Search, Sparkles, Table2,
} from 'lucide-react';
import {
  annual, classArea, classShare, distribution, dominantClass, metricValue,
  selectedTimeline, shareChange, totalArea,
} from './landcoverModel.js';

const INDEX_URL = '/data/landcover/index.json';
const NO_DATA = '#11191a';
const SELECTED = '#ffffff';

function number(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return Number(value).toLocaleString('en-US', {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  });
}

function hexToRgb(hex) {
  const value = hex.replace('#', '');
  return [0, 2, 4].map(index => parseInt(value.slice(index, index + 2), 16));
}

function mix(a, b, amount) {
  const left = hexToRgb(a); const right = hexToRgb(b);
  const channel = index => Math.round(left[index] + (right[index] - left[index]) * amount)
    .toString(16).padStart(2, '0');
  return `#${channel(0)}${channel(1)}${channel(2)}`;
}

function Logo() {
  return <a className="land-logo" href="/" aria-label="UzGeoData home">
    <svg viewBox="0 0 38 38" aria-hidden="true"><path d="M5 7h8v15c0 5 2 8 6 8s6-3 6-8V7h8v16c0 9-5 14-14 14S5 32 5 23V7Z"/><path className="land-logo-bar" d="M13 2h21v5H13z"/></svg>
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
  const valid = points.filter(point => point.share !== null);
  if (valid.length < 2) return <div className="land-chart-empty">More years are needed for a trend.</div>;
  const width = 330; const height = 116; const pad = 13;
  const min = Math.min(...valid.map(point => point.share));
  const max = Math.max(...valid.map(point => point.share));
  const spread = Math.max(max - min, 0.25);
  const x = year => pad + (points.indexOf(year) / Math.max(points.length - 1, 1)) * (width - pad * 2);
  const y = value => height - pad - ((value - min) / spread) * (height - pad * 2);
  const path = valid.map((point, index) => `${index ? 'L' : 'M'}${x(point)},${y(point.share)}`).join(' ');
  const area = `${path} L${x(valid.at(-1))},${height - pad} L${x(valid[0])},${height - pad} Z`;
  return <svg className="land-mini-line" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Land-cover share over time">
    <defs><linearGradient id="land-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".32"/><stop offset="1" stopColor={color} stopOpacity="0"/></linearGradient></defs>
    <path d={area} fill="url(#land-area)"/>
    <path d={path} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke"/>
    {valid.map(point => <circle key={point.year} cx={x(point)} cy={y(point.share)} r="2.6" fill={color}/>) }
    <text x={pad} y="10">{number(max, 1)}%</text><text x={pad} y={height - 1}>{number(min, 1)}%</text>
  </svg>;
}

function Histogram({ model, color, mode }) {
  if (!model.bins.length) return <div className="land-chart-empty">No spatial distribution for this view.</div>;
  return <div className="land-histogram">
    {model.bins.map(bin => <div key={bin.from}>
      <i style={{ height: `${Math.max(bin.count / model.max * 100, 2)}%`, background: color }}/>
      <span>{mode === 'change' ? number(bin.from, 1) : number(bin.to, mode === 'area' ? 0 : 1)}</span>
    </div>)}
  </div>;
}

function Composition({ values, classes }) {
  const total = Object.values(values || {}).reduce((sum, value) => sum + Number(value), 0);
  if (!total) return null;
  return <div className="land-composition" aria-label="Land-cover composition">
    {classes.map(item => {
      const share = Number(values?.[item.code] || 0) / total * 100;
      return share > 0 ? <i key={item.code} title={`${item.name}: ${number(share, 1)}%`}
        style={{ width: `${share}%`, background: item.color }}/> : null;
    })}
  </div>;
}

export default function LandcoverExplorer() {
  const [meta, setMeta] = useState(null);
  const [series, setSeries] = useState(null);
  const [geometry, setGeometry] = useState(null);
  const [error, setError] = useState(null);
  const [year, setYear] = useState(null);
  const [classCode, setClassCode] = useState(5);
  const [mode, setMode] = useState('share');
  const [selectedId, setSelectedId] = useState(null);
  const [hoverId, setHoverId] = useState(null);
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState('insight');
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    let live = true;
    fetch(INDEX_URL).then(response => {
      if (!response.ok) throw new Error(`${response.status} loading ${INDEX_URL}`);
      return response.json();
    }).then(async index => {
      const [observations, basins] = await Promise.all([
        fetch(index.series).then(response => response.json()),
        fetch(index.reference.geometry).then(response => response.json()),
      ]);
      if (!live) return;
      setMeta(index); setSeries(observations); setGeometry(basins);
      const bestYear = [...index.years].sort((a, b) =>
        (index.coverage.byYear[a] || 0) - (index.coverage.byYear[b] || 0) || a - b
      ).at(-1);
      setYear(bestYear);
    }).catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, []);

  useEffect(() => {
    if (!playing || !meta?.years.length) return undefined;
    const timer = setInterval(() => setYear(current => {
      const position = meta.years.indexOf(current);
      return meta.years[(position + 1) % meta.years.length];
    }), 1300);
    return () => clearInterval(timer);
  }, [playing, meta]);

  const classes = meta?.classes || [];
  const classByCode = useMemo(
    () => Object.fromEntries(classes.map(item => [item.code, item])), [classes],
  );
  const activeClass = classByCode[classCode] || classes[0];
  const basinData = series?.basins || {};
  const records = useMemo(() => Object.values(basinData), [basinData]);
  const spatial = useMemo(
    () => meta && year ? distribution(records, year, classCode, mode, meta.years) : { values: [], bins: [], max: 0 },
    [records, year, classCode, mode, meta],
  );
  const maxValue = useMemo(() => {
    if (!spatial.values.length) return 1;
    const sorted = [...spatial.values].sort((a, b) => a - b);
    return Math.max(Math.abs(sorted[Math.floor(sorted.length * .95)] || 0), .01);
  }, [spatial]);

  const visibleId = hoverId || selectedId;
  const nationalRecord = useMemo(() => meta ? {
    pfaf: 'National selection', years: meta.totalsKm2,
  } : null, [meta]);
  const selected = selectedId ? basinData[selectedId] : nationalRecord;
  const visible = visibleId ? basinData[visibleId] : selected;
  const selectedFeature = useMemo(() => geometry?.features.find(
    feature => String(feature.properties.HYBAS_ID) === selectedId,
  ), [geometry, selectedId]);
  const timeline = useMemo(
    () => meta && selected ? selectedTimeline(selected, meta.years, classCode) : [],
    [meta, selected, classCode],
  );

  const national = meta?.totalsKm2?.[year] || {};
  const nationalTotal = Object.values(national).reduce((sum, value) => sum + Number(value), 0);
  const nationalShare = nationalTotal ? Number(national[classCode] || 0) / nationalTotal * 100 : null;
  const currentValue = visible && meta ? metricValue(visible, year, classCode, mode, meta.years) : null;

  const metricLabel = value => {
    if (value === null) return 'No observation';
    if (mode === 'dominant') return classByCode[value]?.name || 'Unknown class';
    if (mode === 'area') return `${number(value, 1)} km²`;
    if (mode === 'change') return `${value > 0 ? '+' : ''}${number(value, 2)} pp`;
    return `${number(value, 1)}%`;
  };

  const featureColor = id => {
    const record = basinData[String(id)];
    const value = record && meta ? metricValue(record, year, classCode, mode, meta.years) : null;
    if (value === null) return NO_DATA;
    if (mode === 'dominant') return classByCode[value]?.color || NO_DATA;
    if (mode === 'change') {
      const amount = Math.min(Math.abs(value) / maxValue, 1);
      return mix('#263134', value < 0 ? '#39a7ff' : '#ff695d', .2 + amount * .8);
    }
    return mix('#172121', activeClass?.color || '#f4d35e', .12 + Math.min(value / maxValue, 1) * .88);
  };

  const searchMatches = useMemo(() => {
    const term = query.trim();
    if (!term) return [];
    return Object.entries(basinData).filter(([id, record]) => id.includes(term) || record.pfaf.includes(term)).slice(0, 7);
  }, [query, basinData]);

  if (error) return <div className="land-fatal"><Sparkles/><h1>The observatory is waiting for data.</h1><p>{error}</p><code>npm run landcover:web</code><a href="/">Return to portal</a></div>;
  if (!meta || !series || !geometry || year === null) return <div className="land-loading"><span/><p>Assembling the basin observatory</p></div>;

  return <div className="land-app">
    <section className="land-stage">
      <MapContainer center={[41.25, 64.4]} zoom={5} minZoom={4} maxZoom={12} zoomControl={false} preferCanvas>
        <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
        <ZoomControl position="bottomleft"/><ScaleControl position="bottomright"/>
        <GeoJSON
          key={`${year}-${classCode}-${mode}-${selectedId}`}
          data={geometry}
          style={feature => {
            const id = String(feature.properties.HYBAS_ID);
            const selectedNow = id === selectedId;
            return {
              color: selectedNow ? SELECTED : mix(featureColor(id), '#ffffff', .2),
              weight: selectedNow ? 2 : .45,
              fillColor: featureColor(id),
              fillOpacity: basinData[id]?.years?.[year] ? .82 : .2,
              opacity: selectedNow ? 1 : .6,
            };
          }}
          onEachFeature={(feature, layer) => {
            const id = String(feature.properties.HYBAS_ID);
            layer.on({
              mouseover: () => setHoverId(id), mouseout: () => setHoverId(null),
              click: () => setSelectedId(id),
            });
          }}
        />
        <MapFocus feature={selectedFeature}/>
      </MapContainer>

      <header className="land-header">
        <Logo/>
        <div className="land-title"><span>ONTOLOGY APPLICATION / 01</span><strong>Basin land-cover observatory</strong></div>
        <nav><a href="/">Portal</a><a href="/ontology.html">Living ontology</a><a href="/hydrography.html">Hydrography</a><a href="/climate.html">Climate</a><a href="/relationships.html">Tables</a><a href="/catalogue.html">Catalogue</a></nav>
      </header>

      <aside className="land-lens">
        <div className="land-eyebrow"><Layers size={13}/> ANALYTICAL LENS <small>{year}</small></div>
        <h1>See the surface <em>change.</em></h1>
        <p>Every colour is a measured relationship between an Earth observation and a BasinATLAS catchment.</p>
        <div className="land-search">
          <Search size={14}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Find HYBAS or Pfafstetter ID"/>
          {!!searchMatches.length && <div>{searchMatches.map(([id, record]) => <button key={id} onClick={() => { setSelectedId(id); setQuery(''); }}><span>Basin {record.pfaf}</span><small>{id}</small></button>)}</div>}
        </div>
        <label>Land-cover signal</label>
        <div className="land-classes">
          {classes.map(item => <button key={item.code} className={item.code === classCode ? 'active' : ''}
            style={{ '--class-color': item.color }} onClick={() => setClassCode(item.code)}><i/>{item.name}</button>)}
        </div>
        <label>Map expression</label>
        <div className="land-modes">
          {[['share', 'Share %'], ['change', 'Annual Δ'], ['area', 'Area km²'], ['dominant', 'Dominant']].map(([key, label]) => <button key={key} className={mode === key ? 'active' : ''} onClick={() => setMode(key)}>{label}</button>)}
        </div>
        <div className="land-ontology-path"><span>ONTOLOGY PATH</span><code>Esri LULC</code><b>hasBasinStatistic</b><code>Basin {selected?.pfaf || '—'}</code></div>
      </aside>

      <aside className="land-insight">
        <div className="land-insight-tabs">
          {[['insight', BarChart3, 'Insight'], ['table', Table2, 'Table'], ['json', Braces, 'JSON']].map(([key, Icon, label]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}><Icon size={12}/>{label}</button>)}
        </div>
        {tab === 'insight' && <div className="land-insight-body">
          <div className="land-feature-id"><MapPin size={13}/><span>{visibleId ? `HYBAS ${visibleId}` : 'ALL MEASURED BASINS'}</span></div>
          <h2>{visibleId ? `Basin ${visible?.pfaf || '—'}` : 'Uzbekistan basin frame'}</h2>
          <div className="land-big-number" style={{ color: activeClass?.color }}>{metricLabel(currentValue)}</div>
          <span className="land-big-caption">{activeClass?.name} · {mode === 'change' ? `change from ${meta.years[meta.years.indexOf(year) - 1] || 'baseline'}` : mode} · {year}</span>
          {visible && <Composition values={annual(visible, year)} classes={classes}/>} 
          <div className="land-mini-stats">
            <div><span>Observed area</span><strong>{number(totalArea(visible, year), 1)} km²</strong></div>
            <div><span>National signal</span><strong>{number(nationalShare, 1)}%</strong></div>
            <div><span>Annual change</span><strong>{number(shareChange(visible, year, classCode, meta.years), 2)} pp</strong></div>
            <div><span>Dominant cover</span><strong>{classByCode[dominantClass(visible, year)]?.name || '—'}</strong></div>
          </div>
          <div className="land-chart-title"><span>TEMPORAL SIGNATURE</span><small>{meta.years[0]}—{meta.years.at(-1)}</small></div>
          <MiniLine points={timeline} color={activeClass?.color}/>
        </div>}
        {tab === 'table' && <div className="land-table-wrap"><table><thead><tr><th>Year</th><th>Area</th><th>Share</th><th>Δ pp</th></tr></thead><tbody>{timeline.map(point => <tr key={point.year}><td>{point.year}</td><td>{number(point.area, 2)}</td><td>{number(point.share, 2)}%</td><td>{number(shareChange(selected, point.year, classCode, meta.years), 2)}</td></tr>)}</tbody></table></div>}
        {tab === 'json' && <div className="land-json"><div><span>LIVE GRAPH PROJECTION</span><a href={meta.series}>Open file <ArrowUpRight size={11}/></a></div><pre>{JSON.stringify({
          '@id': selectedId ? `uz:basin/${selectedId}` : null,
          '@type': 'Basin',
          predicate: meta.ontology.predicate,
          dataset: meta.ontology.subject,
          year,
          observations: annual(selected, year),
        }, null, 2)}</pre></div>}
      </aside>

      <div className="land-map-readout">
        <div><span>MEASURED BASINS</span><strong>{number(meta.coverage.byYear[year] || 0)}</strong></div>
        <div><span>SELECTED SIGNAL</span><strong>{activeClass?.name}</strong></div>
        <div><span>SPATIAL MEDIAN</span><strong>{metricLabel(spatial.values.length ? [...spatial.values].sort((a,b) => a-b)[Math.floor(spatial.values.length / 2)] : null)}</strong></div>
      </div>

      <div className="land-timeline">
        <button className="land-play" onClick={() => setPlaying(current => !current)}>{playing ? <Pause size={14}/> : <Play size={14}/>}</button>
        <div className="land-year-track">
          {meta.years.map(item => <button key={item} className={item === year ? 'active' : ''} onClick={() => { setYear(item); setPlaying(false); }}><i/><span>{item}</span><small>{number(meta.coverage.byYear[item] || 0)} basins</small></button>)}
        </div>
        <div className="land-resolution"><span>SOURCE</span><strong>10 m</strong><i/><span>REDUCTION</span><strong>30 m</strong></div>
      </div>
    </section>

    <section className="land-evidence">
      <div className="land-evidence-intro"><span>THE PRACTICAL ANSWER</span><h2>Where is land cover changing—and by how much?</h2><p>The map is not decoration. Select a class, compare annual share, inspect the distribution, then open the exact basin-year JSON behind the visual.</p></div>
      <div className="land-distribution"><div className="land-section-title"><BarChart3 size={14}/><span>SPATIAL DISTRIBUTION</span><small>{number(spatial.values.length)} observed basins</small></div><Histogram model={spatial} color={activeClass?.color} mode={mode}/><p>Distribution of the selected metric across every measured basin in {year}. Values beyond the 95th percentile share the strongest map colour.</p></div>
      <div className="land-national"><div className="land-section-title"><Database size={14}/><span>SELECTION COMPOSITION</span><small>{year}</small></div><Composition values={national} classes={classes}/><div>{classes.map(item => { const share = nationalTotal ? Number(national[item.code] || 0) / nationalTotal * 100 : 0; return <span key={item.code}><i style={{ background: item.color }}/><b>{item.name}</b><small>{number(share, 1)}%</small></span>; })}</div></div>
    </section>

    <section className="land-provenance">
      <div><Sparkles size={22}/><span>MEASUREMENT, NOT INFERENCE</span></div>
      <p>Impact Observatory / Esri annual land cover is reduced with pixel area over canonical BasinATLAS level-12 polygons. The ontology binds every row to <code>{meta.ontology.predicate}</code>, preserves the HYBAS identifier scheme, and exposes the result as both a relationship table and browser JSON.</p>
      <div className="land-provenance-grid"><span><small>DATASET</small>{meta.ontology.subject}</span><span><small>PREDICATE</small>{meta.ontology.predicate}</span><span><small>REFERENCE</small>{meta.reference.layer}</span><span><small>COVERAGE</small>{number(meta.coverage.percent, 2)}% basin-years</span></div>
    </section>
  </div>;
}
