import React, {useEffect, useMemo, useState} from 'react';
import {
  Activity, ArrowLeft, ArrowUpRight, Database, Droplets, GitBranch,
  Network, Pause, Play, Search, Waves, Waypoints, Zap,
} from 'lucide-react';
import {
  anomalyTimeline, buildReachNetwork, deviationSummary, levelBasinLookup,
  reachNeighborhood, resolveLevelBasin,
} from './ontologyNetworkModel.js';

const DEFAULT_REACH = '40190238';
const json = url => fetch(url).then(response => response.ok
  ? response.json()
  : Promise.reject(new Error(`${response.status} while loading ${url}`)));
const compact = value => new Intl.NumberFormat('en-US', {notation: 'compact', maximumFractionDigits: 1}).format(value || 0);
const number = (value, digits = 1) => value == null
  ? '—'
  : Number(value).toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits});

function anomalyColor(z) {
  if (z == null) return '#7b817f';
  if (z <= -1.5) return '#ff4f45';
  if (z < -0.5) return '#ff9a4c';
  if (z >= 1.5) return '#50dcff';
  if (z > 0.5) return '#64a8ff';
  return '#79e6ae';
}

function anomalyLabel(z) {
  if (z == null) return 'NO TEMPORAL MATCH';
  if (z <= -2) return 'EXTREMELY BELOW NORMAL';
  if (z <= -1) return 'BELOW NORMAL';
  if (z >= 2) return 'EXTREMELY ABOVE NORMAL';
  if (z >= 1) return 'ABOVE NORMAL';
  return 'NEAR NORMAL';
}

function layoutNeighborhood(view, network) {
  const placed = new Map();
  const rootX = 552;
  const rootY = 342;
  placed.set(view.nodes.find(node => node.direction === 'root')?.id, {x: rootX, y: rootY});
  for (const direction of ['upstream', 'downstream']) {
    const depths = new Map();
    view.nodes.filter(node => node.direction === direction).forEach(node => {
      const bucket = depths.get(node.depth) || [];
      bucket.push(node);
      depths.set(node.depth, bucket);
    });
    for (const [depth, nodes] of depths) {
      if (direction === 'upstream') {
        const top = Math.max(52, rootY - Math.min(290, nodes.length * 23));
        const bottom = Math.min(620, rootY + Math.min(290, nodes.length * 23));
        nodes.forEach((node, index) => placed.set(node.id, {
          x: rootX - depth * 99,
          y: nodes.length === 1 ? rootY : top + (index / (nodes.length - 1)) * (bottom - top),
        }));
      } else {
        nodes.forEach((node, index) => placed.set(node.id, {
          x: rootX + depth * 101,
          y: rootY + Math.sin(depth * 1.15) * 38 + index * 12,
        }));
      }
    }
  }
  return view.nodes.map(node => ({...node, ...placed.get(node.id), record: network.byId.get(node.id)}));
}

function edgePath(from, to) {
  const bend = Math.max(34, Math.abs(to.x - from.x) * .48);
  return `M${from.x},${from.y} C${from.x + bend},${from.y} ${to.x - bend},${to.y} ${to.x},${to.y}`;
}

function TemporalDeviation({points, cursor, onCursor, variable}) {
  if (!points.length) return <div className="universe-no-signal"><Activity/><strong>No matched anomaly series</strong><span>This reach has no resolvable level-7 temporal context in the published CFSv2 table.</span></div>;
  const width = 430;
  const height = 178;
  const padX = 12;
  const padY = 16;
  const limit = Math.max(2.5, ...points.map(point => Math.abs(point.z)));
  const zero = height / 2;
  const x = index => padX + (index / Math.max(points.length - 1, 1)) * (width - padX * 2);
  const y = value => zero - (value / limit) * (height / 2 - padY);
  const activeCursor = Math.min(cursor, points.length - 1);
  const active = points[activeCursor];
  const path = points.map((point, index) => `${index ? 'L' : 'M'}${x(index).toFixed(1)},${y(point.z).toFixed(1)}`).join(' ');
  return <div className="deviation-chart">
    <div className="deviation-chart-head"><div><span>BASIN-CONTEXT DEVIATION</span><strong>{variable.replaceAll('_', ' ')}</strong></div><div style={{color: anomalyColor(active.z)}}><b>{active.z > 0 ? '+' : ''}{number(active.z, 2)}</b><small>Z-SCORE</small></div></div>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${variable} anomaly through time`}>
      <line className="zero" x1="0" x2={width} y1={zero} y2={zero}/>
      <line className="guide" x1="0" x2={width} y1={y(1)} y2={y(1)}/>
      <line className="guide" x1="0" x2={width} y1={y(-1)} y2={y(-1)}/>
      {points.map((point, index) => <rect key={point.period} className="deviation-bar" x={x(index) - 2.2} y={Math.min(zero, y(point.z))} width="4.4" height={Math.max(1, Math.abs(zero - y(point.z)))} fill={anomalyColor(point.z)} onClick={() => onCursor(index)}><title>{point.period}: {point.z.toFixed(2)}σ</title></rect>)}
      <path className="deviation-path" d={path}/>
      <line className="time-cursor" x1={x(activeCursor)} x2={x(activeCursor)} y1="4" y2={height - 4}/>
      <circle className="time-pulse" cx={x(activeCursor)} cy={y(active.z)} r="5" style={{'--signal': anomalyColor(active.z)}}/>
    </svg>
    <div className="deviation-axis"><span>{points[0].period}</span><strong>{active.period} · {anomalyLabel(active.z)}</strong><span>{points.at(-1).period}</span></div>
  </div>;
}

function Logo() {
  return <a href="/" className="universe-logo" aria-label="UzGeoData home"><svg viewBox="0 0 38 38"><path d="M5 7h8v15c0 5 2 8 6 8s6-3 6-8V7h8v16c0 9-5 14-14 14S5 32 5 23V7Z"/><path className="bar" d="M13 2h21v5H13z"/></svg><span>UZ<span>GEO</span>DATA</span></a>;
}

export default function OntologyUniverse() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(DEFAULT_REACH);
  const [hoveredId, setHoveredId] = useState(null);
  const [query, setQuery] = useState('');
  const [variable, setVariable] = useState('precipitation');
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(true);

  useEffect(() => {
    let live = true;
    Promise.all([
      json('/data/ontology-graph.json'),
      json('/data/hydrography/relationships.json'),
      json('/data/basin-layers/index.json'),
      json('/data/review/basinatlas/basinatlas_uz_lev07.geojson'),
    ]).then(async ([ontology, hydro, layerIndex, level7]) => {
      const anomalyLayer = layerIndex.layers.find(layer => layer.kind === 'anomaly');
      const anomaly = anomalyLayer ? await json(anomalyLayer.series) : null;
      if (live) setData({ontology, hydro, layerIndex, level7, anomalyLayer, anomaly});
    }).catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, []);

  const network = useMemo(() => buildReachNetwork(data?.hydro?.rivers), [data]);
  const basinById = useMemo(() => new Map((data?.hydro?.basins || []).map(basin => [String(basin.id), basin])), [data]);
  const level7 = useMemo(() => levelBasinLookup(data?.level7?.features), [data]);
  const selected = network.byId.get(String(selectedId));
  const basin12 = selected ? basinById.get(selected.basinId) : null;
  const parent7 = resolveLevelBasin(basin12, level7);
  const points = useMemo(() => anomalyTimeline(data?.anomaly, parent7, variable), [data, parent7, variable]);
  const summary = useMemo(() => deviationSummary(points), [points]);
  const activePoint = points[Math.min(cursor, Math.max(points.length - 1, 0))];

  useEffect(() => { setCursor(0); }, [selectedId, variable, points.length]);
  useEffect(() => {
    if (!playing || points.length < 2) return undefined;
    const timer = window.setInterval(() => setCursor(current => (current + 1) % points.length), 760);
    return () => window.clearInterval(timer);
  }, [playing, points.length]);

  const view = useMemo(() => reachNeighborhood(selectedId, network, {upDepth: 5, downDepth: 5, maxNodes: 82, childrenPerNode: 4}), [selectedId, network]);
  const nodes = useMemo(() => layoutNeighborhood(view, network), [view, network]);
  const positioned = useMemo(() => new Map(nodes.map(node => [node.id, node])), [nodes]);
  const topReaches = useMemo(() => [...network.byId.values()].sort((a, b) => (b.upstreamKm2 || 0) - (a.upstreamKm2 || 0)).slice(0, 6), [network]);
  const results = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return topReaches;
    return [...network.byId.values()].filter(reach => reach.id.includes(term) || String(reach.basinId).includes(term)).slice(0, 8);
  }, [query, network, topReaches]);
  const variables = data?.anomalyLayer?.variables || [];
  const selectReach = id => { setSelectedId(String(id)); setPlaying(true); };

  if (error) return <main className="universe-state"><Zap/><h1>The graph could not wake up.</h1><p>{error}</p><a href="/">Return to portal</a></main>;
  if (!data) return <main className="universe-state loading"><div className="loading-neuron"><i/><i/><i/><b/></div><span>CONNECTING 1.17M RELATIONSHIPS</span><h1>Waking the ontology.</h1></main>;

  const currentColor = anomalyColor(activePoint?.z);
  return <main className="ontology-universe" style={{'--current-signal': currentColor}}>
    <header className="universe-header"><Logo/><div className="universe-title"><span>LIVE ONTOLOGY / HYDROLOGICAL NERVOUS SYSTEM</span><b>Every line is a measured relationship</b></div><nav><a href="/landcover.html">Land cover</a><a href="/climate.html">Climate</a><a href="/hydrography.html">Hydrography</a><a href="/relationships.html">Tables</a></nav><a className="back" href="/"><ArrowLeft/> Portal</a></header>

    <section className="universe-shell">
      <aside className="universe-rail">
        <div className="rail-heading"><span>ENTITY FINDER</span><h1>Touch the<br/><em>network.</em></h1><p>Select any visible neuron. The graph reroutes around that reach and resolves its basin context.</p></div>
        <label className="reach-search"><Search/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Reach or basin ID"/><small>{compact(data.hydro.counts.rivers)} reaches</small></label>
        <div className="reach-results"><span>{query ? 'MATCHING ENTITIES' : 'HIGH-FLOW SIGNALS'}</span>{results.map(reach => <button key={reach.id} className={reach.id === selectedId ? 'active' : ''} onClick={() => selectReach(reach.id)}><i/><span><strong>REACH {reach.id}</strong><small>Order {reach.strahlerOrder} · {number(reach.dischargeCms)} m³/s</small></span><ArrowUpRight/></button>)}</div>
        <div className="rail-legend"><span>FLOW DIRECTION</span><p><i className="up"/> upstream branches</p><p><i className="down"/> downstream trunk</p><p><i className="signal"/> temporal signal</p></div>
        <div className="rail-truth"><Database/><p><strong>Measurement boundary</strong><span>Temporal values are inherited from the containing level-7 basin. No reach-level sensor value is implied.</span></p></div>
      </aside>

      <section className="universe-stage">
        <div className="stage-head"><div><i/><span>GRAPH ACTIVE</span><b>{nodes.length} ENTITIES · {view.edges.length} RELATIONSHIPS IN FOCUS</b></div><div><span>{compact(data.ontology.counts.relationshipLinks)}</span> measured edges <b>·</b> {data.ontology.counts.datasets} datasets</div></div>
        <svg className="neural-canvas" viewBox="0 0 1080 760" role="img" aria-label="Animated upstream and downstream relationship tree for the selected river reach">
          <defs><filter id="neural-glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="3.2" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter><radialGradient id="core-fill"><stop offset="0" stopColor="#fff"/><stop offset=".24" stopColor={currentColor}/><stop offset="1" stopColor="#161918"/></radialGradient></defs>
          <g className="ambient-neurons">{Array.from({length: 42}, (_, index) => <circle key={index} cx={(index * 193) % 1060 + 10} cy={(index * 127) % 620 + 30} r={index % 5 === 0 ? 1.4 : .7} style={{'--delay': `${(index % 11) * .21}s`}}/>)}</g>
          <g className="neural-edges">{view.edges.map((edge, index) => {const from = positioned.get(edge.from); const to = positioned.get(edge.to); if (!from || !to) return null; const path = edgePath(from, to); return <g key={`${edge.from}-${edge.to}`} className={edge.direction}><path className="edge-haze" d={path}/><path className="edge-signal" d={path} style={{'--delay': `${index * -0.08}s`}}/>{index % 3 === 0 && <circle r="1.8"><animateMotion dur={`${2.5 + index % 5 * .35}s`} repeatCount="indefinite" path={path}/></circle>}</g>})}</g>
          <g className="context-links"><path d="M552 360 C552 500 392 555 392 660"/><path d="M416 680 C480 680 487 680 542 680"/><path d="M590 680 C650 680 661 680 718 680"/><path d="M774 680 C833 680 844 680 900 680"/></g>
          <g className="neural-nodes">{nodes.map((node, index) => {const focus = node.id === selectedId; const hover = node.id === hoveredId; const radius = focus ? 13 : Math.max(3.2, Math.min(7, (node.record?.strahlerOrder || 1) * .82)); return <g key={node.id} className={`${node.direction} ${focus ? 'selected' : ''}`} transform={`translate(${node.x} ${node.y})`} onClick={() => selectReach(node.id)} onMouseEnter={() => setHoveredId(node.id)} onMouseLeave={() => setHoveredId(null)} role="button" tabIndex="0" onKeyDown={event => (event.key === 'Enter' || event.key === ' ') && selectReach(node.id)}><circle className="synapse-ring" r={radius + 8}/><circle className="synapse" r={radius} style={{fill: focus ? 'url(#core-fill)' : undefined}}/><circle className="synapse-core" r={Math.max(1.2, radius * .28)}/>{(focus || hover || node.record?.strahlerOrder >= 8) && <text x={focus ? 20 : 13} y="3">{focus ? `SELECTED · ${node.id}` : node.id}</text>}<title>Reach {node.id} · order {node.record?.strahlerOrder} · {number(node.record?.dischargeCms)} m³/s</title></g>})}</g>
          <g className="context-nodes">
            <g transform="translate(392 680)"><circle r="25"/><Droplets x="-9" y="-9" size="18"/><text y="39">BASIN L12</text><text className="value" y="50">{selected?.basinId || 'UNRESOLVED'}</text></g>
            <g transform="translate(566 680)"><circle r="25"/><GitBranch x="-9" y="-9" size="18"/><text y="39">PFAF PARENT L7</text><text className="value" y="50">{parent7 || 'UNRESOLVED'}</text></g>
            <g transform="translate(746 680)"><circle r="25"/><Activity x="-9" y="-9" size="18"/><text y="39">HAS BASIN ANOMALY</text><text className="value" y="50">{data.anomalyLayer?.id || 'NO TABLE'}</text></g>
            <g transform="translate(930 680)"><circle className="signal-context" r="25"/><Zap x="-9" y="-9" size="18"/><text y="39">OBSERVES</text><text className="value" y="50">{variable.replaceAll('_', ' ')}</text></g>
          </g>
          <g className="direction-labels"><text x="38" y="28">HEADWATERS / UPSTREAM</text><text x="878" y="28">OUTLET / DOWNSTREAM</text><text x="450" y="625">ONTOLOGY RESOLUTION PATH</text></g>
        </svg>
        <div className="stage-foot"><span><i/> CLICK A SYNAPSE TO RE-CENTER</span><p><Waypoints/> {compact(data.hydro.counts.downstreamLinks)} routed reach links</p><p><Droplets/> {compact(data.hydro.counts.riverBasinLinks)} reach-to-basin links</p></div>
      </section>

      <aside className="signal-panel">
        <div className="entity-kicker"><span>SELECTED ENTITY</span><b>RIVER REACH</b></div>
        <div className="entity-heading"><div><Waves/></div><span><small>HYRIV_ID</small><h2>{selected?.id || '—'}</h2></span><i style={{background: currentColor}}/></div>
        <div className="entity-measures"><p><span>STRAHLER ORDER</span><strong>{selected?.strahlerOrder ?? '—'}</strong></p><p><span>UPSTREAM AREA</span><strong>{compact(selected?.upstreamKm2)} <small>km²</small></strong></p><p><span>MEAN DISCHARGE</span><strong>{number(selected?.dischargeCms)} <small>m³/s</small></strong></p><p><span>REACH LENGTH</span><strong>{number(selected?.lengthKm, 2)} <small>km</small></strong></p></div>
        <div className="signal-controls"><label><span>TEMPORAL PROPERTY</span><select value={variable} onChange={event => setVariable(event.target.value)}>{variables.map(item => <option value={item.code} key={item.code}>{item.label}</option>)}</select></label><button onClick={() => setPlaying(value => !value)} aria-label={playing ? 'Pause temporal animation' : 'Play temporal animation'}>{playing ? <Pause/> : <Play/>}<span>{playing ? 'PAUSE SIGNAL' : 'PLAY SIGNAL'}</span></button></div>
        <TemporalDeviation points={points} cursor={cursor} onCursor={setCursor} variable={variable}/>
        <div className="signal-summary"><div><span>CURRENT DEVIATION</span><strong style={{color: currentColor}}>{activePoint?.z > 0 ? '+' : ''}{number(activePoint?.z, 2)}σ</strong><small>{activePoint?.period || 'no matched period'}</small></div><p><span>RANGE</span><b>{number(summary.minimum, 2)}σ → +{number(summary.maximum, 2)}σ</b></p><p><span>MEAN ABS. DEVIATION</span><b>{number(summary.meanAbsolute, 2)}σ</b></p></div>
        <div className="semantic-path"><span>MEASURED SEMANTIC PATH</span><ol><li><b>Reach {selected?.id}</b><small>withinBasin</small></li><li><b>Basin {selected?.basinId || 'unresolved'}</b><small>subBasinOf · level 7</small></li><li><b>{parent7 || 'No level-7 match'}</b><small>hasBasinAnomaly</small></li><li><b>NCEP CFSv2</b><small>observes · {variable.replaceAll('_', ' ')}</small></li></ol></div>
        <a className="open-observatory" href="/climate.html"><span>OPEN FULL CLIMATE OBSERVATORY<small>Map every basin and period</small></span><ArrowUpRight/></a>
      </aside>
    </section>
  </main>;
}
