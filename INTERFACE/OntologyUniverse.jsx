import React, {useEffect, useMemo, useRef, useState} from 'react';
import {
  Activity, ArrowLeft, ArrowUpRight, ChevronDown, ChevronLeft, ChevronRight, ChevronUp,
  Crosshair, Database, Download, Droplets, GitBranch, MapPin, Minus, Network, Pause,
  Play, Plus, RotateCcw, Search, Waves, Waypoints, Zap,
} from 'lucide-react';
import {
  anomalyTimeline, buildReachNetwork, deviationSummary, findHydroEntities, levelBasinLookup,
  resolveLevelBasin, traceReachNetwork,
} from './ontologyNetworkModel.js';
import {downloadPayload, overlayFeatureCollection, temporalSeriesCsv} from './ontologyExportModel.js';

const DEFAULT_REACH = '40197927';
const DEFAULT_VARIABLE = 'soil_moisture_25cm';
const EMPTY = [];
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

function layoutTraceTree(view, network) {
  const root = view.nodes.find(node => node.direction === 'root');
  if (!root) return [];
  const children = new Map();
  for (const edge of view.edges.filter(edge => edge.direction === 'upstream')) {
    const branch = children.get(edge.to) || [];
    branch.push(edge.from);
    children.set(edge.to, branch);
  }
  const rawY = new Map();
  let leaf = 0;
  const assignY = id => {
    const branch = children.get(id) || [];
    if (!branch.length) {
      rawY.set(id, leaf++);
      return rawY.get(id);
    }
    const positions = branch.map(assignY);
    const middle = (Math.min(...positions) + Math.max(...positions)) / 2;
    rawY.set(id, middle);
    return middle;
  };
  assignY(root.id);
  const rootX = 650;
  const top = 50;
  const bottom = 612;
  const leafSpan = Math.max(leaf - 1, 1);
  const placed = new Map();
  for (const node of view.nodes.filter(node => node.direction !== 'downstream')) {
    placed.set(node.id, {
      x: rootX - (node.depth / Math.max(view.maxUpDepth, 1)) * 612,
      y: leaf === 1 ? (top + bottom) / 2 : top + (rawY.get(node.id) / leafSpan) * (bottom - top),
    });
  }
  const rootY = placed.get(root.id).y;
  const downstream = view.nodes.filter(node => node.direction === 'downstream');
  const downstreamDepth = Math.max(downstream.length, 1);
  for (const node of downstream) {
    placed.set(node.id, {
      x: rootX + (node.depth / downstreamDepth) * 380,
      y: rootY + Math.sin(node.depth * .85) * 18,
    });
  }
  return view.nodes.map(node => ({...node, ...placed.get(node.id), record: network.byId.get(node.id)}));
}

function edgePath(from, to) {
  const bend = Math.max(34, Math.abs(to.x - from.x) * .48);
  return `M${from.x},${from.y} C${from.x + bend},${from.y} ${to.x - bend},${to.y} ${to.x},${to.y}`;
}

function coordinateLines(geometry) {
  if (!geometry) return [];
  if (geometry.type === 'LineString') return [geometry.coordinates];
  if (geometry.type === 'MultiLineString' || geometry.type === 'Polygon') return geometry.coordinates;
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.flat();
  return [];
}

function TraceMiniMap({rivers, basins, boundary, districts, selectedReachId, selectedBasinId, currentColor}) {
  const width = 304;
  const height = 174;
  const coordinates = [...rivers, ...basins].flatMap(feature => coordinateLines(feature.geometry).flat());
  if (!coordinates.length) return null;
  let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
  for (const [lon, lat] of coordinates) {
    minLon = Math.min(minLon, lon); maxLon = Math.max(maxLon, lon);
    minLat = Math.min(minLat, lat); maxLat = Math.max(maxLat, lat);
  }
  const lonPad = Math.max((maxLon - minLon) * .08, .035);
  const latPad = Math.max((maxLat - minLat) * .08, .035);
  minLon -= lonPad; maxLon += lonPad; minLat -= latPad; maxLat += latPad;
  const midLat = (minLat + maxLat) / 2;
  const lonFactor = Math.cos(midLat * Math.PI / 180);
  const scale = Math.min((width - 12) / Math.max((maxLon - minLon) * lonFactor, .001), (height - 12) / Math.max(maxLat - minLat, .001));
  const drawWidth = (maxLon - minLon) * lonFactor * scale;
  const drawHeight = (maxLat - minLat) * scale;
  const offsetX = (width - drawWidth) / 2;
  const offsetY = (height - drawHeight) / 2;
  const project = ([lon, lat]) => [offsetX + (lon - minLon) * lonFactor * scale, offsetY + (maxLat - lat) * scale];
  const path = geometry => coordinateLines(geometry).map(line => line.map((point, index) => {
    const [x, y] = project(point);
    return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ') + (geometry.type.includes('Polygon') ? ' Z' : '')).join(' ');
  const labelPoint = feature => {
    const points = coordinateLines(feature.geometry).flat();
    if (!points.length) return null;
    const bounds = points.reduce((box, [lon, lat]) => ({
      minLon: Math.min(box.minLon, lon), maxLon: Math.max(box.maxLon, lon),
      minLat: Math.min(box.minLat, lat), maxLat: Math.max(box.maxLat, lat),
    }), {minLon: Infinity, maxLon: -Infinity, minLat: Infinity, maxLat: -Infinity});
    return project([(bounds.minLon + bounds.maxLon) / 2, (bounds.minLat + bounds.maxLat) / 2]);
  };
  return <aside className="trace-minimap">
    <div className="minimap-head"><span>LIVE SPATIAL TRACE</span><b>{rivers.length} REACHES · {basins.length} BASINS</b></div>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Map of the exact traced reaches and their related basin polygons">
      <defs><filter id="map-glow"><feGaussianBlur stdDeviation="1.7" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter><clipPath id="map-clip"><rect width={width} height={height}/></clipPath></defs>
      <g clipPath="url(#map-clip)">
        {(boundary?.features || EMPTY).map((feature, index) => <path className="map-boundary" d={path(feature.geometry)} key={`boundary-${index}`}/>)}
        {(districts || EMPTY).map(feature => <path className="map-district" d={path(feature.geometry)} key={`district-${feature.properties.pcode}`}/>)}
        {basins.map(feature => <path className="map-basin" d={path(feature.geometry)} key={feature.properties.HYBAS_ID}/>)}
        {basins.filter(feature => String(feature.properties.HYBAS_ID) === selectedBasinId).map(feature => <path className="map-basin-selected" d={path(feature.geometry)} style={{stroke: currentColor}} key={`selected-basin-${selectedBasinId}`}/>)}
        {rivers.map(feature => <path className="map-river" d={path(feature.geometry)} key={feature.properties.HYRIV_ID}/>)}
        {rivers.filter(feature => String(feature.properties.HYRIV_ID) === selectedReachId).map(feature => <path className="map-selected" d={path(feature.geometry)} style={{stroke: currentColor}} key={`selected-${selectedReachId}`}/>)}
        {(districts || EMPTY).map(feature => {const point = labelPoint(feature); return point && point[0] >= 0 && point[0] <= width && point[1] >= 0 && point[1] <= height ? <text className="map-district-label" x={point[0]} y={point[1]} key={`label-${feature.properties.pcode}`}>{feature.district?.nameEn || feature.properties.nameEn}</text> : null})}
      </g>
    </svg>
    <div className="minimap-legend"><span><i className="district"/> district context</span><span><i className="basin"/> basins</span><span><i className="river"/> reaches</span></div>
  </aside>;
}

function TemporalDeviation({points, cursor, onCursor, variable, unit}) {
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
    <div className="deviation-chart-head"><div><span>BASIN-CONTEXT DEVIATION</span><strong>{variable.replaceAll('_', ' ')}</strong><small>{number(active.value, 5)} {unit || 'source units'} · stored value</small></div><div style={{color: anomalyColor(active.z)}}><b>{active.z > 0 ? '+' : ''}{number(active.z, 2)}</b><small>Z-SCORE</small></div></div>
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
  const [selectedBasinId, setSelectedBasinId] = useState(null);
  const [hoveredId, setHoveredId] = useState(null);
  const [query, setQuery] = useState('');
  const [variable, setVariable] = useState(DEFAULT_VARIABLE);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [graphZoom, setGraphZoom] = useState(1);
  const [graphPan, setGraphPan] = useState({x: 0, y: 0});
  const [graphDragging, setGraphDragging] = useState(false);
  const [mobilePanel, setMobilePanel] = useState(null);
  const [exporting, setExporting] = useState(null);
  const [exportError, setExportError] = useState(null);
  const graphDrag = useRef(null);

  useEffect(() => {
    let live = true;
    Promise.all([
      json('/data/ontology-graph.json'),
      json('/data/hydrography/relationships.json'),
      json('/data/hydrography/rivers.geojson'),
      json('/data/hydrography/basins.geojson'),
      json('/data/hydrography/boundary.geojson'),
      json('/data/hydrography/admin-basin-links.json'),
      json('/data/admin/adm2.geojson'),
      json('/data/basin-layers/index.json'),
      json('/data/review/basinatlas/basinatlas_uz_lev07.geojson'),
    ]).then(async ([ontology, hydro, riversGeo, basinsGeo, boundary, adminLinks, districtsGeo, layerIndex, level7]) => {
      const anomalyLayer = layerIndex.layers.find(layer => layer.kind === 'anomaly');
      const anomaly = anomalyLayer ? await json(anomalyLayer.series) : null;
      if (live) setData({ontology, hydro, riversGeo, basinsGeo, boundary, adminLinks, districtsGeo, layerIndex, level7, anomalyLayer, anomaly});
    }).catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, []);

  const network = useMemo(() => buildReachNetwork(data?.hydro?.rivers), [data]);
  const basinNetwork = useMemo(() => buildReachNetwork(data?.hydro?.basins), [data]);
  const basinById = useMemo(() => new Map((data?.hydro?.basins || []).map(basin => [String(basin.id), basin])), [data]);
  const level7 = useMemo(() => levelBasinLookup(data?.level7?.features), [data]);
  const riverGeometry = useMemo(() => new Map((data?.riversGeo?.features || []).map(feature => [String(feature.properties?.HYRIV_ID), feature])), [data]);
  const basinGeometry = useMemo(() => new Map((data?.basinsGeo?.features || []).map(feature => [String(feature.properties?.HYBAS_ID), feature])), [data]);
  const level7Geometry = useMemo(() => new Map((data?.level7?.features || []).map(feature => [String(feature.properties?.HYBAS_ID), feature])), [data]);
  const districtGeometry = useMemo(() => new Map((data?.districtsGeo?.features || []).map(feature => [feature.properties?.pcode, feature])), [data]);
  const districtByCode = useMemo(() => new Map((data?.adminLinks?.districts || []).map(district => [district.pcode, district])), [data]);
  const provinceByCode = useMemo(() => new Map((data?.adminLinks?.provinces || []).map(province => [province.pcode, province])), [data]);
  const districtsByBasin = useMemo(() => new Map(Object.entries(data?.adminLinks?.byBasin || {}).map(([basinId, links]) => [basinId,
    Object.entries(links.adm2 || {}).sort((left, right) => right[1] - left[1]).map(([pcode, overlapKm2]) => ({
      ...districtByCode.get(pcode), pcode, overlapKm2,
    })),
  ])), [data, districtByCode]);
  const focusType = selectedBasinId ? 'basin' : 'reach';
  const focusId = selectedBasinId || selectedId;
  const focusNetwork = focusType === 'basin' ? basinNetwork : network;
  const selectedReach = network.byId.get(String(selectedId));
  const basin12 = selectedBasinId ? basinById.get(selectedBasinId) : selectedReach ? basinById.get(selectedReach.basinId) : null;
  const parent7 = resolveLevelBasin(basin12, level7);
  const parent7Feature = level7Geometry.get(String(parent7));
  const districtContext = districtsByBasin.get(String(basin12?.id)) || EMPTY;
  const primaryProvince = provinceByCode.get(districtContext[0]?.parent);
  const currentDistrictFeatures = districtContext.slice(0, 3).map(district => {
    const feature = districtGeometry.get(district.pcode);
    return feature ? {...feature, district} : null;
  }).filter(Boolean);
  const districtLabelForBasin = basinId => {
    const matches = districtsByBasin.get(String(basinId)) || EMPTY;
    return matches.length ? matches.slice(0, 2).map(district => district.nameEn || district.nameUz || district.pcode).join(' / ') : 'No district overlap';
  };
  const variables = data?.anomalyLayer?.variables || EMPTY;
  const variableOptions = useMemo(() => variables.map(item => ({
    ...item,
    points: anomalyTimeline(data?.anomaly, parent7, item.code).length,
  })), [data, parent7, variables]);
  const availableVariables = variableOptions.filter(item => item.points > 0);
  const unavailableVariables = variableOptions.filter(item => item.points === 0);
  const points = useMemo(() => anomalyTimeline(data?.anomaly, parent7, variable), [data, parent7, variable]);
  const summary = useMemo(() => deviationSummary(points), [points]);
  const activePoint = points[Math.min(cursor, Math.max(points.length - 1, 0))];
  const variableMeta = variables.find(item => item.code === variable);

  useEffect(() => { setCursor(0); }, [focusId, variable, points.length]);
  useEffect(() => {
    if (variableOptions.length && !variableOptions.some(item => item.code === variable && item.points > 0)) {
      setVariable(variableOptions.find(item => item.points > 0)?.code || variableOptions[0].code);
    }
  }, [parent7, variable, variableOptions]);
  useEffect(() => {
    if (!playing || points.length < 2) return undefined;
    const timer = window.setInterval(() => setCursor(current => (current + 1) % points.length), 760);
    return () => window.clearInterval(timer);
  }, [playing, points.length]);

  const view = useMemo(() => traceReachNetwork(focusId, focusNetwork), [focusId, focusNetwork]);
  const nodes = useMemo(() => layoutTraceTree(view, focusNetwork), [view, focusNetwork]);
  const positioned = useMemo(() => new Map(nodes.map(node => [node.id, node])), [nodes]);
  const traceBasinIds = useMemo(() => new Set(focusType === 'basin'
    ? nodes.map(node => node.id)
    : nodes.map(node => node.record?.basinId).filter(Boolean)), [focusType, nodes]);
  const traceRivers = useMemo(() => focusType === 'basin'
    ? [...network.byId.values()].filter(reach => traceBasinIds.has(reach.basinId)).map(reach => riverGeometry.get(reach.id)).filter(Boolean)
    : nodes.map(node => riverGeometry.get(node.id)).filter(Boolean), [focusType, network, nodes, riverGeometry, traceBasinIds]);
  const traceBasins = useMemo(() => [...traceBasinIds].map(id => basinGeometry.get(id)).filter(Boolean), [traceBasinIds, basinGeometry]);
  const traceDirectionById = useMemo(() => new Map(nodes.map(node => [node.id, node.direction])), [nodes]);
  const upstreamBasinIds = useMemo(() => new Set(nodes
    .filter(node => node.direction !== 'downstream')
    .map(node => focusType === 'basin' ? node.id : node.record?.basinId)
    .filter(Boolean)), [focusType, nodes]);
  const upstreamRivers = useMemo(() => focusType === 'basin'
    ? [...network.byId.values()]
      .filter(reach => upstreamBasinIds.has(reach.basinId))
      .map(reach => riverGeometry.get(reach.id))
      .filter(Boolean)
    : nodes
      .filter(node => node.direction !== 'downstream')
      .map(node => riverGeometry.get(node.id))
      .filter(Boolean), [focusType, network, nodes, riverGeometry, upstreamBasinIds]);
  const signalBasins = useMemo(() => new Set(Object.entries(data?.anomaly?.basins || {}).filter(([, periods]) => Object.values(periods).some(cells => cells[DEFAULT_VARIABLE])).map(([id]) => id)), [data]);
  const topReaches = useMemo(() => [...network.byId.values()].filter(reach => {
    const basin = basinById.get(reach.basinId);
    return signalBasins.has(resolveLevelBasin(basin, level7));
  }).sort((a, b) => (b.upstreamKm2 || 0) - (a.upstreamKm2 || 0)).slice(0, 6), [network, basinById, signalBasins, level7]);
  const results = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return topReaches.map(record => ({type: 'reach', record}));
    return findHydroEntities(term, [...network.byId.values()], [...basinById.values()]);
  }, [query, network, basinById, topReaches]);
  const resetGraphView = () => { setGraphZoom(1); setGraphPan({x: 0, y: 0}); };
  const selectReach = id => { setSelectedBasinId(null); setSelectedId(String(id)); resetGraphView(); setMobilePanel(null); setPlaying(true); };
  const selectBasin = id => { setSelectedBasinId(String(id)); resetGraphView(); setMobilePanel(null); setPlaying(true); };
  const selectGraphEntity = id => focusType === 'basin' ? selectBasin(id) : selectReach(id);
  const zoomGraph = change => setGraphZoom(current => Math.max(.65, Math.min(3.2, Number((current + change).toFixed(2)))));
  const panGraph = (x, y) => setGraphPan(current => ({x: current.x + x, y: current.y + y}));
  const graphKeyDown = event => {
    if (event.key === '+' || event.key === '=') { event.preventDefault(); zoomGraph(.25); }
    if (event.key === '-' || event.key === '_') { event.preventDefault(); zoomGraph(-.25); }
    if (event.key === '0') { event.preventDefault(); resetGraphView(); }
    const step = event.shiftKey ? 120 : 55;
    if (event.key === 'ArrowLeft') { event.preventDefault(); panGraph(-step, 0); }
    if (event.key === 'ArrowRight') { event.preventDefault(); panGraph(step, 0); }
    if (event.key === 'ArrowUp') { event.preventDefault(); panGraph(0, -step); }
    if (event.key === 'ArrowDown') { event.preventDefault(); panGraph(0, step); }
  };
  const startGraphDrag = event => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    if (event.target.closest?.('.neural-nodes g[role="button"]')) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const viewBox = event.currentTarget.viewBox.baseVal;
    graphDrag.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      pan: graphPan,
      scaleX: viewBox.width / Math.max(bounds.width, 1),
      scaleY: viewBox.height / Math.max(bounds.height, 1),
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setGraphDragging(true);
  };
  const moveGraphDrag = event => {
    const drag = graphDrag.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    setGraphPan({
      x: drag.pan.x - (event.clientX - drag.x) * drag.scaleX,
      y: drag.pan.y - (event.clientY - drag.y) * drag.scaleY,
    });
  };
  const endGraphDrag = event => {
    if (!graphDrag.current || graphDrag.current.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    graphDrag.current = null;
    setGraphDragging(false);
  };
  const activePeriod = activePoint?.period || data?.anomalyLayer?.periods?.[Math.min(cursor, Math.max((data?.anomalyLayer?.periods?.length || 1) - 1, 0))] || null;
  const safeFocusId = String(focusType === 'basin' ? basin12?.pfafId || focusId : focusId).replace(/[^a-zA-Z0-9_-]+/g, '-');
  const administrativeContext = basinId => {
    const districts = districtsByBasin.get(String(basinId)) || EMPTY;
    const province = provinceByCode.get(districts[0]?.parent);
    return {
      district: districts[0]?.nameEn || districts[0]?.nameUz || districts[0]?.pcode || null,
      districtCode: districts[0]?.pcode || null,
      districts: districts.map(item => item.nameEn || item.nameUz || item.pcode).join(' | ') || null,
      overlapKm2: districts[0]?.overlapKm2 ?? null,
      province: province?.nameEn || province?.nameUz || province?.pcode || null,
      provinceCode: province?.pcode || districts[0]?.parent || null,
    };
  };
  const temporalContext = basinId => {
    const basin = basinById.get(String(basinId));
    const basin7Id = resolveLevelBasin(basin, level7);
    const cell = activePeriod ? data?.anomaly?.basins?.[String(basin7Id)]?.[activePeriod]?.[variable] : null;
    return {basin, basin7Id, cell};
  };
  const featureWithProperties = (feature, properties) => feature ? ({
    ...feature,
    properties: {...(feature.properties || {}), ...properties},
  }) : null;
  const reachRole = feature => {
    const reachId = String(feature?.properties?.HYRIV_ID);
    const reach = network.byId.get(reachId);
    const direction = focusType === 'basin' ? traceDirectionById.get(reach?.basinId) : traceDirectionById.get(reachId);
    return direction === 'root' ? 'selected' : direction || 'national-context';
  };
  const enrichReach = feature => {
    const reachId = String(feature?.properties?.HYRIV_ID);
    const reach = network.byId.get(reachId);
    const basinId = reach?.basinId || String(feature?.properties?.HYBAS_L12 || '');
    const admin = administrativeContext(basinId);
    const temporal = temporalContext(basinId);
    return featureWithProperties(feature, {
      UZG_ENTITY: 'river-reach', UZG_ROLE: reachRole(feature), UZG_FOCUS_TYPE: focusType, UZG_FOCUS_ID: focusId,
      UZG_BASIN_L12: basinId || null, UZG_PFAF_L12: temporal.basin?.pfafId || null, UZG_BASIN_L7: temporal.basin7Id,
      UZG_DISTRICT: admin.district, UZG_DISTRICT_CODE: admin.districtCode, UZG_DISTRICTS: admin.districts,
      UZG_PROVINCE: admin.province, UZG_PROVINCE_CODE: admin.provinceCode, UZG_ADMIN_OVERLAP_KM2: admin.overlapKm2,
      UZG_ADMIN_METHOD: 'inherited from level-12 basin polygon overlap', UZG_DATASET: 'HydroRIVERS v1.0',
      UZG_TEMP_DATASET: data?.anomaly?.dataset || data?.anomalyLayer?.dataset || null,
      UZG_TEMP_VARIABLE: variable, UZG_TEMP_PERIOD: activePeriod, UZG_TEMP_VALUE: temporal.cell?.v ?? null,
      UZG_TEMP_UNIT: variableMeta?.unit || null, UZG_TEMP_Z: temporal.cell?.z ?? null, UZG_TEMP_CLASS: temporal.cell?.c || null,
      UZG_TEMP_SCOPE: 'level-7 basin context; not a reach measurement',
    });
  };
  const enrichBasin = feature => {
    const basinId = String(feature?.properties?.HYBAS_ID);
    const admin = administrativeContext(basinId);
    const temporal = temporalContext(basinId);
    const direction = focusType === 'basin' ? traceDirectionById.get(basinId) : (basinId === String(basin12?.id) ? 'selected-context' : 'trace-context');
    return featureWithProperties(feature, {
      UZG_ENTITY: 'basin-level-12', UZG_ROLE: direction === 'root' ? 'selected' : direction || 'national-context',
      UZG_FOCUS_TYPE: focusType, UZG_FOCUS_ID: focusId, UZG_BASIN_L12: basinId,
      UZG_PFAF_L12: temporal.basin?.pfafId || feature?.properties?.PFAF_ID || null, UZG_BASIN_L7: temporal.basin7Id,
      UZG_DISTRICT: admin.district, UZG_DISTRICT_CODE: admin.districtCode, UZG_DISTRICTS: admin.districts,
      UZG_PROVINCE: admin.province, UZG_PROVINCE_CODE: admin.provinceCode, UZG_ADMIN_OVERLAP_KM2: admin.overlapKm2,
      UZG_ADMIN_METHOD: 'measured polygon overlap', UZG_DATASET: 'HydroBASINS/BasinATLAS level 12',
      UZG_TEMP_DATASET: data?.anomaly?.dataset || data?.anomalyLayer?.dataset || null,
      UZG_TEMP_VARIABLE: variable, UZG_TEMP_PERIOD: activePeriod, UZG_TEMP_VALUE: temporal.cell?.v ?? null,
      UZG_TEMP_UNIT: variableMeta?.unit || null, UZG_TEMP_Z: temporal.cell?.z ?? null, UZG_TEMP_CLASS: temporal.cell?.c || null,
      UZG_TEMP_SCOPE: 'inherited from containing level-7 basin',
    });
  };
  const enrichLevel7 = feature => {
    const basin7Id = String(feature?.properties?.HYBAS_ID);
    const cell = activePeriod ? data?.anomaly?.basins?.[basin7Id]?.[activePeriod]?.[variable] : null;
    return featureWithProperties(feature, {
      UZG_ENTITY: 'temporal-basin-level-7', UZG_ROLE: basin7Id === String(parent7) ? 'selected-temporal-context' : 'national-context',
      UZG_DATASET: 'HydroBASINS/BasinATLAS level 7', UZG_TEMP_DATASET: data?.anomaly?.dataset || data?.anomalyLayer?.dataset || null,
      UZG_TEMP_VARIABLE: variable, UZG_TEMP_PERIOD: activePeriod, UZG_TEMP_VALUE: cell?.v ?? null,
      UZG_TEMP_UNIT: variableMeta?.unit || null, UZG_TEMP_Z: cell?.z ?? null, UZG_TEMP_CLASS: cell?.c || null,
      UZG_TEMP_SCOPE: 'direct level-7 basin aggregate',
    });
  };
  const enrichDistrict = feature => featureWithProperties(feature, {
    UZG_ENTITY: 'administrative-district',
    UZG_ROLE: currentDistrictFeatures.some(item => item.properties?.pcode === feature?.properties?.pcode) ? 'selected-context' : 'national-context',
    UZG_DATASET: 'Uzbekistan ADM2 boundary', UZG_TEMP_SCOPE: 'administrative overlay only; no temporal value assigned',
  });
  const exportMetadata = (name, scope, featureCount) => ({
    name, generatedAt: new Date().toISOString(), scope, featureCount,
    selectedEntity: {type: focusType, id: focusId, pfafId: basin12?.pfafId || null},
    temporalProperty: {dataset: data?.anomaly?.dataset || data?.anomalyLayer?.dataset || null, variable, unit: variableMeta?.unit || null, period: activePeriod},
    provenance: 'Existing published UzGeoData HydroRIVERS, HydroBASINS/BasinATLAS, ADM2 overlap, and CFSv2 anomaly records; no simulated values.',
    measurementBoundary: 'Reach temporal fields are inherited level-7 basin context, not direct reach observations.',
  });
  const requestExport = (key, callback) => {
    setExportError(null);
    setExporting(key);
    window.setTimeout(() => {
      try { callback(); }
      catch (cause) { setExportError(cause?.message || 'The export could not be prepared.'); }
      finally { setExporting(null); }
    }, 25);
  };
  const downloadUpstream = () => requestExport('upstream', () => {
    const features = upstreamRivers.map(enrichReach);
    const overlay = overlayFeatureCollection(features, exportMetadata('uzgeodata-upstream-reaches', 'selected reach/basin plus every stored upstream reach; downstream reaches excluded', features.length));
    downloadPayload(`uzgeodata-${safeFocusId}-upstream-reaches.geojson`, overlay, 'application/geo+json');
  });
  const downloadSeries = () => requestExport('series', () => {
    const csv = temporalSeriesCsv({
      entityType: focusType, entityId: focusType === 'basin' ? basin12?.pfafId || focusId : selectedReach?.id || focusId,
      basin12: basin12?.id || null, basin7: parent7,
      districts: districtContext.map(item => item.nameEn || item.nameUz || item.pcode).join(' | '),
      province: primaryProvince?.nameEn || primaryProvince?.nameUz || primaryProvince?.pcode || null,
      dataset: data?.anomaly?.dataset || data?.anomalyLayer?.dataset || null, variable, unit: variableMeta?.unit || null,
    }, points);
    downloadPayload(`uzgeodata-${safeFocusId}-${variable}-series.csv`, csv, 'text/csv;charset=utf-8');
  });
  const downloadTraceOverlay = () => requestExport('trace', () => {
    const features = [
      ...traceRivers.map(enrichReach), ...traceBasins.map(enrichBasin),
      ...currentDistrictFeatures.map(enrichDistrict), enrichLevel7(parent7Feature),
    ].filter(Boolean);
    const overlay = overlayFeatureCollection(features, exportMetadata('uzgeodata-current-ontology-overlay', 'complete visible ontology trace with reach, basin, temporal-basin, and administrative geometries', features.length));
    downloadPayload(`uzgeodata-${safeFocusId}-trace-overlay.geojson`, overlay, 'application/geo+json');
  });
  const downloadNationalOverlay = () => requestExport('national', () => {
    const features = [
      ...(data?.riversGeo?.features || EMPTY).map(enrichReach),
      ...(data?.basinsGeo?.features || EMPTY).map(enrichBasin),
      ...(data?.districtsGeo?.features || EMPTY).map(enrichDistrict),
      ...(data?.level7?.features || EMPTY).map(enrichLevel7),
    ];
    const overlay = overlayFeatureCollection(features, exportMetadata('uzgeodata-national-ontology-overlay', 'entire published national overlay: all reaches, level-12 basins, districts, and level-7 temporal basins', features.length));
    downloadPayload(`uzgeodata-national-${variable}-${activePeriod || 'no-period'}-overlay.geojson`, overlay, 'application/geo+json');
  });

  if (error) return <main className="universe-state"><Zap/><h1>The graph could not wake up.</h1><p>{error}</p><a href="/">Return to portal</a></main>;
  if (!data) return <main className="universe-state loading"><div className="loading-neuron"><i/><i/><i/><b/></div><span>CONNECTING 1.17M RELATIONSHIPS</span><h1>Waking the ontology.</h1></main>;

  const currentColor = anomalyColor(activePoint?.z);
  const rootPosition = positioned.get(focusId);
  const graphViewWidth = 1080 / graphZoom;
  const graphViewHeight = 760 / graphZoom;
  const focusWeight = graphZoom > 1 ? 1 - 1 / graphZoom : 0;
  const graphCenterX = 540 + ((rootPosition?.x || 540) - 540) * focusWeight + graphPan.x;
  const graphCenterY = 380 + ((rootPosition?.y || 380) - 380) * focusWeight + graphPan.y;
  const graphViewBox = `${graphCenterX - graphViewWidth / 2} ${graphCenterY - graphViewHeight / 2} ${graphViewWidth} ${graphViewHeight}`;
  return <main className="ontology-universe" style={{'--current-signal': currentColor}}>
    <header className="universe-header"><Logo/><div className="universe-title"><span>LIVE ONTOLOGY / HYDROLOGICAL NERVOUS SYSTEM</span><b>Every line is a measured relationship</b></div><nav><a href="/landcover.html">Land cover</a><a href="/climate.html">Climate</a><a href="/hydrography.html">Hydrography</a><a href="/relationships.html">Tables</a></nav><a className="back" href="/"><ArrowLeft/> Portal</a></header>

    <section className="universe-shell">
      <div className="universe-mobile-tools" aria-label="Ontology panels">
        <button type="button" className={mobilePanel === 'entities' ? 'active' : ''}
          aria-expanded={mobilePanel === 'entities'} onClick={() => setMobilePanel(current => current === 'entities' ? null : 'entities')}>
          <Search/> Entities
        </button>
        <button type="button" className={mobilePanel === 'details' ? 'active' : ''}
          aria-expanded={mobilePanel === 'details'} onClick={() => setMobilePanel(current => current === 'details' ? null : 'details')}>
          <Activity/> Details
        </button>
      </div>
      <aside className={`universe-rail ${mobilePanel === 'entities' ? 'mobile-open' : ''}`}>
        <div className="rail-heading"><span>ENTITY FINDER</span><h1>Touch the<br/><em>network.</em></h1><p>Select any visible neuron. The chart rebuilds the complete stored upstream tree and downstream trunk, while the minimap traces their real geometry and basin polygons.</p></div>
        <label className="reach-search"><Search/><input value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => {if(event.key === 'Enter' && results[0]){event.preventDefault();results[0].type === 'basin' ? selectBasin(results[0].record.id) : selectReach(results[0].record.id)}}} placeholder="Reach, HYBAS or PFAF ID"/><small>{compact(data.hydro.counts.rivers)} + {compact(data.hydro.counts.basins)}</small></label>
        <div className="reach-results"><span>{query ? 'MATCHING REACHES + BASINS' : 'HIGH-FLOW SIGNALS'}</span>{results.map(({type, record}) => {const active = focusType === type && focusId === String(record.id); const district = districtLabelForBasin(type === 'basin' ? record.id : record.basinId); return <button key={`${type}-${record.id}`} className={`${active ? 'active' : ''} entity-${type}`} onClick={() => type === 'basin' ? selectBasin(record.id) : selectReach(record.id)}><i/><span><strong>{type === 'basin' ? `BASIN ${record.pfafId}` : `REACH ${record.id}`}</strong><small>{district} · {type === 'basin' ? `HYBAS ${record.id}` : `order ${record.strahlerOrder}`}</small></span><ArrowUpRight/></button>})}</div>
        <div className="rail-legend"><span>FLOW DIRECTION</span><p><i className="up"/> upstream branches</p><p><i className="down"/> downstream trunk</p><p><i className="signal"/> temporal signal</p></div>
        <div className="rail-truth"><Database/><p><strong>Measurement boundary</strong><span>Temporal values are inherited from the containing level-7 basin. No reach-level sensor value is implied.</span></p></div>
      </aside>

      <section className="universe-stage">
        <div className="stage-head"><div><i/><span>EXACT {focusType.toUpperCase()} TRACE</span><b>{view.upstreamCount} UPSTREAM · {view.downstreamCount} DOWNSTREAM</b></div><div><span>{compact(view.edges.length)}</span> visible flow links <b>·</b> {traceBasins.length} related basins</div></div>
        <div className="graph-controls" aria-label="Graph zoom controls"><button type="button" onClick={() => zoomGraph(.25)} aria-label="Zoom graph in"><Plus/></button><output aria-live="polite">{Math.round(graphZoom * 100)}%</output><button type="button" onClick={() => zoomGraph(-.25)} aria-label="Zoom graph out"><Minus/></button><button type="button" onClick={resetGraphView} aria-label="Reset graph zoom and position"><RotateCcw/></button></div>
        <div className="graph-pan-controls" aria-label="Graph movement controls">
          <button type="button" className="north" onClick={() => panGraph(0, -70)} aria-label="Pan graph north"><ChevronUp/></button>
          <button type="button" className="west" onClick={() => panGraph(-70, 0)} aria-label="Pan graph west"><ChevronLeft/></button>
          <button type="button" className="home" onClick={resetGraphView} aria-label="Center and reset graph"><Crosshair/></button>
          <button type="button" className="east" onClick={() => panGraph(70, 0)} aria-label="Pan graph east"><ChevronRight/></button>
          <button type="button" className="south" onClick={() => panGraph(0, 70)} aria-label="Pan graph south"><ChevronDown/></button>
        </div>
        <svg className={`neural-canvas ${graphDragging ? 'is-dragging' : ''}`} viewBox={graphViewBox}
          onWheel={event => { event.preventDefault(); zoomGraph(event.deltaY < 0 ? .15 : -.15); }}
          onPointerDown={startGraphDrag} onPointerMove={moveGraphDrag}
          onPointerUp={endGraphDrag} onPointerCancel={endGraphDrag}
          onDoubleClick={() => zoomGraph(.25)} onKeyDown={graphKeyDown} tabIndex="0"
          role="img" aria-label={`Animated upstream and downstream relationship tree for the selected ${focusType}. Drag or use arrow keys to pan; use mouse wheel, plus and minus keys, or the visible controls to zoom.`}>
          <defs><filter id="neural-glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="3.2" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter><radialGradient id="core-fill"><stop offset="0" stopColor="#fff"/><stop offset=".24" stopColor={currentColor}/><stop offset="1" stopColor="#161918"/></radialGradient></defs>
          <g className="ambient-neurons">{Array.from({length: 42}, (_, index) => <circle key={index} cx={(index * 193) % 1060 + 10} cy={(index * 127) % 620 + 30} r={index % 5 === 0 ? 1.4 : .7} style={{'--delay': `${(index % 11) * .21}s`}}/>)}</g>
          <g className="neural-edges">{view.edges.map((edge, index) => {const from = positioned.get(edge.from); const to = positioned.get(edge.to); if (!from || !to) return null; const path = edgePath(from, to); const particleStep = Math.max(1, Math.ceil(view.edges.length / 32)); const signalStep = Math.max(1, Math.floor(view.edges.length / 120)); const carriesSignal = edge.direction === 'downstream' || index % signalStep === 0; return <g key={`${edge.from}-${edge.to}`} className={edge.direction}><path className="edge-haze" d={path}/>{carriesSignal && <path className="edge-signal" d={path} style={{'--delay': `${index * -0.03}s`}}/>}{index % particleStep === 0 && <circle r="1.8"><animateMotion dur={`${2.5 + index % 5 * .35}s`} repeatCount="indefinite" path={path}/></circle>}</g>})}</g>
          <g className="context-links"><path d={`M${rootPosition?.x || 650} ${rootPosition?.y || 360} C${rootPosition?.x || 650} 520 392 555 392 660`}/><path d="M416 680 C480 680 487 680 542 680"/><path d="M590 680 C650 680 661 680 718 680"/><path d="M774 680 C833 680 844 680 900 680"/></g>
          <g className="neural-nodes">{nodes.map((node, index) => {const focus = node.id === focusId; const hover = node.id === hoveredId; const nodeOrder = node.record?.strahlerOrder || node.record?.order || 1; const nodeBasin = focusType === 'basin' ? node.id : node.record?.basinId; const nodeDistrict = districtLabelForBasin(nodeBasin); const radius = focus ? 11 : Math.max(1.2, Math.min(5.2, nodeOrder * .62)); return <g key={node.id} className={`${node.direction} ${focus ? 'selected' : ''}`} transform={`translate(${node.x} ${node.y})`} onClick={() => selectGraphEntity(node.id)} onMouseEnter={() => setHoveredId(node.id)} onMouseLeave={() => setHoveredId(null)} role="button" tabIndex="0" onKeyDown={event => {if(event.key === 'Enter' || event.key === ' '){event.preventDefault();selectGraphEntity(node.id)}}}><circle className="synapse-ring" r={radius + 5}/><circle className="synapse" r={radius} style={{fill: focus ? 'url(#core-fill)' : undefined}}/><circle className="synapse-core" r={Math.max(.7, radius * .28)}/>{(focus || hover || (nodeOrder >= 8 && index % 35 === 0)) && <text x={focus ? 18 : 11} y="3">{focus ? `SELECTED · ${node.id} · ${nodeDistrict}` : `${node.id} · ${nodeDistrict}`}</text>}<title>{focusType === 'basin' ? `Basin ${node.record?.pfafId} · HYBAS ${node.id}` : `Reach ${node.id} · order ${nodeOrder} · ${number(node.record?.dischargeCms)} m³/s`} · approximately {nodeDistrict}</title></g>})}</g>
          <g className="context-nodes">
            <g transform="translate(392 680)"><circle r="25"/><Droplets x="-9" y="-9" size="18"/><text y="39">BASIN L12</text><text className="value" y="50">{basin12?.id || 'UNRESOLVED'}</text></g>
            <g transform="translate(566 680)"><circle r="25"/><GitBranch x="-9" y="-9" size="18"/><text y="39">PFAF PARENT L7</text><text className="value" y="50">{parent7 || 'UNRESOLVED'}</text></g>
            <g transform="translate(746 680)"><circle r="25"/><Activity x="-9" y="-9" size="18"/><text y="39">HAS BASIN ANOMALY</text><text className="value" y="50">{data.anomalyLayer?.id || 'NO TABLE'}</text></g>
            <g transform="translate(930 680)"><circle className="signal-context" r="25"/><Zap x="-9" y="-9" size="18"/><text y="39">OBSERVES</text><text className="value" y="50">{variable.replaceAll('_', ' ')}</text></g>
          </g>
          <g className="direction-labels"><text x="38" y="28">{focusType === 'basin' ? 'UPSTREAM SUB-BASINS' : 'HEADWATERS / UPSTREAM'}</text><text x="878" y="28">OUTLET / DOWNSTREAM</text><text x="450" y="625">ONTOLOGY RESOLUTION PATH</text></g>
        </svg>
        <TraceMiniMap rivers={traceRivers} basins={traceBasins} boundary={data.boundary} districts={currentDistrictFeatures} selectedReachId={focusType === 'reach' ? selectedId : null} selectedBasinId={focusType === 'basin' ? selectedBasinId : null} currentColor={currentColor}/>
        <div className="stage-foot"><span><i/> CLICK A SYNAPSE TO RE-TRACE GRAPH + MAP</span><p><Waypoints/> {compact(nodes.length)} exact {focusType} entities</p><p><Droplets/> {traceBasins.length} linked polygons · {compact(traceRivers.length)} reaches</p></div>
      </section>

      <aside className={`signal-panel ${mobilePanel === 'details' ? 'mobile-open' : ''}`}>
        <div className="entity-kicker"><span>SELECTED ENTITY</span><b>{focusType === 'basin' ? 'LEVEL-12 BASIN' : 'RIVER REACH'}</b></div>
        <div className="entity-heading"><div>{focusType === 'basin' ? <GitBranch/> : <Waves/>}</div><span><small>{focusType === 'basin' ? 'PFAF_ID' : 'HYRIV_ID'}</small><h2>{focusType === 'basin' ? basin12?.pfafId : selectedReach?.id || '—'}</h2></span><i style={{background: currentColor}}/></div>
        {focusType === 'basin'
          ? <div className="entity-measures"><p><span>HYBAS ID</span><strong>{basin12?.id ?? '—'}</strong></p><p><span>UPSTREAM AREA</span><strong>{compact(basin12?.upstreamKm2)} <small>km²</small></strong></p><p><span>SUB-BASIN AREA</span><strong>{number(basin12?.areaKm2, 1)} <small>km²</small></strong></p><p><span>INSIDE UZBEKISTAN</span><strong>{number(basin12?.uzbekistanPercent, 1)} <small>%</small></strong></p></div>
          : <div className="entity-measures"><p><span>STRAHLER ORDER</span><strong>{selectedReach?.strahlerOrder ?? '—'}</strong></p><p><span>UPSTREAM AREA</span><strong>{compact(selectedReach?.upstreamKm2)} <small>km²</small></strong></p><p><span>MEAN DISCHARGE</span><strong>{number(selectedReach?.dischargeCms)} <small>m³/s</small></strong></p><p><span>REACH LENGTH</span><strong>{number(selectedReach?.lengthKm, 2)} <small>km</small></strong></p></div>}
        <div className="admin-context"><MapPin/><p><span>APPROXIMATE ADMINISTRATIVE LOCATION</span><strong>{districtContext.length ? `${districtContext.slice(0, 3).map(district => district.nameEn || district.nameUz || district.pcode).join(' · ')}${districtContext.length > 3 ? ` +${districtContext.length - 3}` : ''}` : 'No measured district overlap'}</strong><small>{districtContext.length ? `${primaryProvince?.nameEn || 'Province unresolved'} · inherited from level-12 basin ${basin12?.id} polygon overlap${focusType === 'reach' ? '; not a direct reach assignment' : ''}` : 'This basin is one of the records without an administrative overlay.'}</small></p></div>
        <div className="signal-controls"><label><span>TEMPORAL PROPERTY · {availableVariables.length}/{variables.length} AVAILABLE HERE</span><select value={variable} onChange={event => setVariable(event.target.value)}>{variableOptions.map(item => <option value={item.code} key={item.code} disabled={!item.points}>{item.label}{item.points ? ` · ${item.points} periods` : ' · no basin values'}</option>)}</select></label><button onClick={() => setPlaying(value => !value)} aria-label={playing ? 'Pause temporal animation' : 'Play temporal animation'}>{playing ? <Pause/> : <Play/>}<span>{playing ? 'PAUSE SIGNAL' : 'PLAY SIGNAL'}</span></button></div>
        {unavailableVariables.length > 0 && <div className="coverage-warning"><Database/><p><strong>Source coverage gap</strong><span>{unavailableVariables.map(item => item.label).join(', ')} {unavailableVariables.length === 1 ? 'has' : 'have'} no stored CFSv2 land-cell values for this basin. The selector will not fabricate them.</span></p></div>}
        <TemporalDeviation points={points} cursor={cursor} onCursor={setCursor} variable={variable} unit={variableMeta?.unit}/>
        <div className="signal-summary"><div><span>CURRENT DEVIATION</span><strong style={{color: currentColor}}>{activePoint?.z > 0 ? '+' : ''}{number(activePoint?.z, 2)}σ</strong><small>{activePoint?.period || 'no matched period'}</small></div><p><span>RANGE</span><b>{number(summary.minimum, 2)}σ → +{number(summary.maximum, 2)}σ</b></p><p><span>MEAN ABS. DEVIATION</span><b>{number(summary.meanAbsolute, 2)}σ</b></p></div>
        <div className="static-et"><span>EVAPOTRANSPIRATION DISTINCTION</span><p><b>{number(parent7Feature?.properties?.aet_mm_syr, 0)} mm/year</b><small>Actual evapotranspiration climatology from BasinATLAS; a static long-term average, not an interannual time series. CFSv2 provides potential evaporation as a separate land-surface flux.</small></p></div>
        <div className="semantic-path"><span>MEASURED SEMANTIC PATH</span><ol>{focusType === 'reach' && <li><b>Reach {selectedReach?.id}</b><small>withinBasin</small></li>}<li><b>Basin {basin12?.id || 'unresolved'}</b><small>{focusType === 'basin' ? `PFAF · ${basin12?.pfafId}` : 'subBasinOf · level 7'}</small></li><li><b>{parent7 || 'No level-7 match'}</b><small>subBasinOf · level 7 · hasBasinAnomaly</small></li><li><b>NCEP CFSv2</b><small>observes · {variable.replaceAll('_', ' ')}</small></li></ol></div>
        <section className="ontology-downloads" aria-label="Download ontology data">
          <div className="download-heading"><span>EXPORT REAL LINKED DATA</span><small>GeoJSON keeps geometry + ontology context</small></div>
          <div className="download-grid">
            <button onClick={downloadUpstream} disabled={Boolean(exporting)}><Download/><span><b>{exporting === 'upstream' ? 'PREPARING...' : 'UPSTREAM REACHES'}</b><small>{compact(upstreamRivers.length)} lines · GeoJSON</small></span></button>
            <button onClick={downloadSeries} disabled={Boolean(exporting) || !points.length}><Download/><span><b>{exporting === 'series' ? 'PREPARING...' : 'SELECTED PROPERTY'}</b><small>{points.length} periods · CSV</small></span></button>
            <button onClick={downloadTraceOverlay} disabled={Boolean(exporting)}><Download/><span><b>{exporting === 'trace' ? 'PREPARING...' : 'VISIBLE OVERLAY'}</b><small>{compact(traceRivers.length + traceBasins.length + currentDistrictFeatures.length + (parent7Feature ? 1 : 0))} features · GeoJSON</small></span></button>
            <button onClick={downloadNationalOverlay} disabled={Boolean(exporting)}><Download/><span><b>{exporting === 'national' ? 'PREPARING...' : 'FULL DATASET OVERLAY'}</b><small>{compact((data.riversGeo?.features?.length || 0) + (data.basinsGeo?.features?.length || 0) + (data.districtsGeo?.features?.length || 0) + (data.level7?.features?.length || 0))} features · GeoJSON</small></span></button>
          </div>
          <p className="download-scope"><Database/> Upstream excludes the downstream trunk. Full overlay contains all published reaches, L12/L7 basins and districts with the active {variable.replaceAll('_', ' ')} period attached.</p>
          {exportError && <p className="download-error" role="alert">{exportError}</p>}
        </section>
        <a className="open-observatory" href="/climate.html"><span>OPEN FULL CLIMATE OBSERVATORY<small>Map every basin and period</small></span><ArrowUpRight/></a>
      </aside>
    </section>
  </main>;
}
