import { useEffect, useMemo, useState } from 'react';
import L from 'leaflet';
import { GeoJSON, MapContainer, TileLayer, ZoomControl } from 'react-leaflet';
import {
  ArrowDown, ArrowRight, Building2, Check, Database, Droplets, FileArchive,
  File, FlaskConical, Grid3X3, HardDrive, Layers3, Leaf, LoaderCircle,
  LockKeyhole, LogOut, Menu, Minus, Mountain, Network, Orbit, Pause, Play, Plus,
  RotateCcw, Search, ShieldAlert, Trash2, Trees, UploadCloud, Wheat, X
} from 'lucide-react';

const datasets = [
  { atlasNumber:185, title:'Protected Areas', category:'Biodiversity', type:'LPKX', size:'0.4 MB', access:'Free', icon:Leaf, desc:'Sixty-two protected-area polygons with designation, location and recorded area attributes.' },
  { atlasNumber:205, title:'Earthquakes 1990–2024', category:'Hazards & terrain', type:'LPKX', size:'0.8 MB', access:'Free', icon:Orbit, desc:'Regional earthquake observations with magnitude, depth, location and event time.' },
  { atlasNumber:52, title:'Water Management Zones', category:'Water', type:'LPKX', size:'0.2 MB', access:'Free', icon:Droplets, desc:'Irrigated areas and water-management zones digitized for national-scale analysis.' },
  { atlasNumber:207, title:'Flood Risk', category:'Hazards & terrain', type:'LPKX', size:'0.4 MB', access:'Free', icon:Layers3, desc:'Catchment-level riverine flood risk scores and standardized risk categories.' },
  { atlasNumber:92, title:'National Land Cover', category:'Land & agriculture', type:'LPKX', size:'971 MB', access:'Request', icon:Grid3X3, desc:'The archive’s largest classified raster package, retained in its original ArcGIS format.' },
  { atlasNumber:118, title:'Maximum NDVI 2004–2024', category:'Land & agriculture', type:'LPKX', size:'132 MB', access:'Request', icon:Mountain, desc:'Long-term maximum vegetation-index surface for agricultural and ecosystem assessment.' },
];

const useCases = [
  { n:'01', sector:'Water security', title:'Plan water allocation', icon:Droplets, question:'Where are demand, deficit and infrastructure pressure converging?', outcome:'Prioritize basin interventions and irrigation-network investment.', data:['Water stress','Annual runoff','Canal density'], users:'Basin authorities · Water agencies' },
  { n:'02', sector:'Climate resilience', title:'Prepare for climate change', icon:Orbit, question:'Which territories show persistent warming, drying or vegetation stress?', outcome:'Build climate baselines and target adaptation measures.', data:['Temperature trends','Water deficit','PDSI'], users:'Planners · Climate analysts' },
  { n:'03', sector:'Agriculture', title:'Monitor productive land', icon:Wheat, question:'How are crop vigor, salinity and land productivity changing?', outcome:'Direct field surveys and support resilient farm management.', data:['NDVI & EVI','Soil salinity','Land productivity'], users:'Agriculture agencies · Agronomists' },
  { n:'04', sector:'Disaster risk', title:'Assess exposure', icon:ShieldAlert, question:'Where do communities and assets overlap known environmental hazards?', outcome:'Support screening, preparedness and risk-sensitive planning.', data:['Flood risk','Earthquakes','Mudflow zones'], users:'Emergency services · Engineers' },
  { n:'05', sector:'Nature & carbon', title:'Protect ecosystems', icon:Trees, question:'Which habitats carry the greatest biodiversity and restoration value?', outcome:'Prioritize protection, restoration and carbon investment.', data:['Protected areas','Forest integrity','Carbon potential'], users:'Conservation bodies · NGOs' },
  { n:'06', sector:'Research', title:'Build reproducible evidence', icon:FlaskConical, question:'Can source layers be compared across themes, regions and time?', outcome:'Create cited analysis without rebuilding the data inventory.', data:['134 indexed layers','Source metadata','Catalog relationships'], users:'Universities · Research teams' },
];

function Logo({ href = '#top' }) {
  return <a href={href} className="logo" aria-label="UzGeoData home">
    <svg viewBox="0 0 38 38" aria-hidden="true"><path d="M5 7h8v15c0 5 2 8 6 8s6-3 6-8V7h8v16c0 9-5 14-14 14S5 32 5 23V7Z"/><path className="logo-bar" d="M13 2h21v5H13z"/></svg>
    <span>UZ<span className="accent">GEO</span>DATA</span>
  </a>
}

function Header({ onAccess }) {
  const [open, setOpen] = useState(false);
  return <header className="site-header">
    <Logo />
    <button className="menu-button" onClick={() => setOpen(!open)} aria-label="Toggle menu" aria-expanded={open} aria-controls="primary-navigation">{open ? <X/> : <Menu/>}</button>
    <nav id="primary-navigation" className={open ? 'open' : ''} onClick={() => setOpen(false)}>
      <a href="#catalog">Data catalog</a><a href="#map">Map explorer</a><a href="#ontology">Ontology</a><a href="#solutions">Use cases</a><a href="#about">Standards</a>
    </nav>
    <button className="button button-small desktop-cta" onClick={onAccess}>Request access <ArrowRight size={16}/></button>
  </header>
}

function Hero({ onExplore, onAccess }) {
  return <section className="hero" id="top">
    <div className="hero-image" />
    <div className="hero-grid" />
    <div className="hero-content">
      <div className="eyebrow"><span className="pulse"/> Uzbekistan environmental data portal</div>
      <h1>Map what<br/><span>matters.</span></h1>
      <p className="hero-copy">Curated environmental geodata for the people shaping Uzbekistan. Atlas vectors, analysis-ready rasters and specialist datasets—organized, documented and ready to work.</p>
      <div className="hero-actions">
        <button className="button" onClick={onExplore}>Explore data <ArrowDown size={17}/></button>
        <button className="text-button" onClick={onAccess}>Request a dataset <ArrowRight size={17}/></button>
      </div>
    </div>
    <div className="hero-stats">
      <div><strong>134</strong><small>Atlas packages catalogued</small></div>
      <div><strong>5</strong><small>Interactive map layers</small></div>
      <div><strong>1.6<span>GB</span></strong><small>Indexed source volume</small></div>
    </div>
    <div className="coordinates">41.3775° N&nbsp;&nbsp;&nbsp; 64.5853° E</div>
    <div className="scroll-note"><span>Scroll to discover</span><ArrowDown size={14}/></div>
  </section>
}

function Catalog({ onRequest }) {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState('All data');
  const categories = ['All data', ...new Set(datasets.map(dataset => dataset.category))];
  const shown = useMemo(() => datasets.filter(d => (active === 'All data' || d.category === active) && (`${d.title} ${d.desc} ${d.type}`).toLowerCase().includes(query.toLowerCase())), [query, active]);
  return <section className="section catalog-section" id="catalog">
    <div className="section-head">
      <div><div className="kicker">01 / Featured data</div><h2>Built for real<br/>decisions.</h2></div>
      <p>A focused selection from the environmental atlas. Source packages are indexed with English titles, access status, source filenames and package sizes.</p>
    </div>
    <div className="catalog-tools">
      <div className="search-box"><Search size={20}/><input aria-label="Search featured datasets" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search datasets, formats or themes..."/><span>{shown.length} results</span></div>
      <div className="filters" aria-label="Dataset themes">{categories.map(c => <button aria-pressed={active === c} className={active === c ? 'active' : ''} onClick={() => setActive(c)} key={c}>{c}</button>)}</div>
    </div>
    <div className="dataset-grid">
      {shown.map((d, i) => <article className="dataset-card" key={d.title} style={{'--delay': `${i * 45}ms`}}>
        <div className="dataset-top"><span className="data-icon"><d.icon size={22}/></span><span className={`access ${d.access.toLowerCase()}`}>{d.access}</span></div>
        <div className="dataset-code">ATLAS / {d.atlasNumber} · {d.category.toUpperCase()}</div>
        <h3>{d.title}</h3><p>{d.desc}</p>
        <div className="dataset-meta"><span><FileArchive size={15}/>{d.type}</span><span><Database size={15}/>{d.size}</span></div>
        <button onClick={() => d.access === 'Free' ? document.getElementById('map').scrollIntoView({behavior:'smooth'}) : onRequest(d.title)}>{d.access === 'Free' ? 'Explore on map' : 'Request access'} <ArrowRight size={17}/></button>
      </article>)}
      {shown.length === 0 && <div className="empty-state"><Search size={30}/><h3>No exact match</h3><p>Try a broader theme or clear your filters.</p><button onClick={() => {setQuery(''); setActive('All data')}}>Clear search</button></div>}
    </div>
    <a href="#map" className="catalog-link">Browse all 134 atlas datasets <ArrowRight size={18}/></a>
  </section>
}

const mapColors = {'protected-areas':'#ff5a1f', earthquakes:'#ff6a2d', 'water-management':'#45bad5', 'glacial-lakes':'#c9edf4', 'flood-risk':'#ffb14a'};
const domainAliases = { Forests: 'Forests & carbon' };
const normalizeDomain = category => domainAliases[category] || category;
const prettyKey = key => ({name:'Name',type:'Type',location:'Location',area_ha:'Area (ha)',date:'Date',magnitude:'Magnitude',depth_km:'Depth (km)',place:'Location',longitude:'Longitude',latitude:'Latitude',region:'Region',risk:'Risk class',risk_score:'Risk score',area_km2:'Area (km²)'})[key] || key.replaceAll('_',' ');
function popupNode(feature, title) {
  const box = document.createElement('div'); box.className = 'map-popup';
  const heading = document.createElement('strong'); heading.textContent = title; box.appendChild(heading);
  Object.entries(feature.properties || {}).filter(([,value]) => value !== null && value !== '' && value !== ' ').slice(0, 6).forEach(([key,value]) => {
    const row = document.createElement('div'); const label = document.createElement('span'); const data = document.createElement('b');
    label.textContent = prettyKey(key); data.textContent = typeof value === 'number' ? Number(value.toFixed(2)).toLocaleString() : String(value); row.append(label,data); box.appendChild(row);
  });
  return box;
}

function EnvironmentalMap() {
  const [layers, setLayers] = useState([]);
  const [active, setActive] = useState('protected-areas');
  const [geoData, setGeoData] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All themes');
  useEffect(() => { Promise.all([fetch('/data/map-layers.json').then(r=>r.json()),fetch('/data/archive-catalog.json').then(r=>r.json())]).then(([mapLayers,items])=>{setLayers(mapLayers);setCatalog(items)}) }, []);
  useEffect(() => { const layer = layers.find(item => item.id === active); if (!layer) return; setGeoData(null); fetch(layer.url).then(r=>r.json()).then(setGeoData) }, [active,layers]);
  const current = layers.find(layer => layer.id === active);
  const categories = ['All themes',...new Set(catalog.map(item=>normalizeDomain(item.category)))];
  const filtered = catalog.filter(item => (category === 'All themes' || normalizeDomain(item.category) === category) && `${item.title} ${item.sourceTitle} ${normalizeDomain(item.category)}`.toLowerCase().includes(query.toLowerCase()));
  const layerStyle = feature => {
    if (active === 'flood-risk') { const score = Number(feature.properties?.risk_score || 0); return {color:score>4?'#ff3f1f':score>3?'#ff7a2c':'#ffb14a',weight:.8,fillOpacity:.28}; }
    return {color:mapColors[active],weight:1.1,fillColor:mapColors[active],fillOpacity:active === 'water-management' ? .28 : .17};
  };
  const pointToLayer = (feature, latlng) => L.circleMarker(latlng,{radius:active === 'earthquakes' ? Math.max(2,Number(feature.properties?.magnitude || 2)*1.15) : 4,color:mapColors[active],weight:1,fillColor:mapColors[active],fillOpacity:active === 'earthquakes' ? .48 : .8});
  return <section className="map-explorer" id="map"><div className="map-intro"><div><div className="kicker">02 / Interactive atlas</div><h2>See the data.<br/><span>Read the terrain.</span></h2></div><p>Five source layers have been optimized for live exploration. Pan, zoom, switch themes and inspect individual features directly from the atlas archive.</p></div>
    <div className="map-workspace"><div className="map-stage"><MapContainer center={[41.2,64.6]} zoom={5} minZoom={4} maxZoom={12} zoomControl={false} preferCanvas>
      <TileLayer attribution='&copy; OpenStreetMap contributors' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"/>
      <ZoomControl position="bottomright"/>
      {geoData && <GeoJSON key={active} data={geoData} style={layerStyle} pointToLayer={pointToLayer} onEachFeature={(feature,layer)=>layer.bindPopup(popupNode(feature,current?.title || 'Feature'),{maxWidth:300})}/>} 
    </MapContainer>{!geoData && <div className="map-loading"><LoaderCircle className="spin"/> Loading layer</div>}<div className="map-readout"><span>UZBEKISTAN / WGS 84</span><strong>{current?.features?.toLocaleString() || '—'} FEATURES</strong></div></div>
      <aside className="map-panel"><div className="layer-heading"><span>LIVE LAYERS</span><small>{layers.length} / 134 web-ready</small></div><div className="layer-buttons">{layers.map(layer=><button key={layer.id} aria-pressed={active===layer.id} className={active===layer.id?'active':''} onClick={()=>setActive(layer.id)}><i style={{background:mapColors[layer.id]}}/><span><strong>{layer.title}</strong><small>{layer.features.toLocaleString()} features · {layer.geometry}</small></span><ArrowRight size={14}/></button>)}</div>
        <div className="archive-index"><div className="layer-heading"><span>FULL ARCHIVE INDEX</span><small>{filtered.length} packages</small></div><div className="archive-search"><Search size={15}/><input aria-label="Search full archive" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search all layers..."/></div><select aria-label="Filter archive by theme" value={category} onChange={e=>setCategory(e.target.value)}>{categories.map(item=><option key={item}>{item}</option>)}</select><div className="archive-results">{filtered.slice(0,60).map(item=><div key={item.id}><span>{item.atlasNumber || '—'}</span><p><strong>{item.title}</strong><small>{normalizeDomain(item.category)} · {(item.size/1024/1024).toFixed(item.size>10*1024*1024?0:1)} MB</small></p></div>)}</div>{filtered.length>60&&<div className="archive-more">+ {filtered.length-60} more matching packages</div>}</div>
      </aside></div>
  </section>
}

// Layout only. What each node *is* comes from /data/ontology-graph.json, which the
// build projects from the stored graph — titles are no longer parsed at render time.
const domainLayout = {
  'uz:theme/climate': {x:270,y:175}, 'uz:theme/infrastructure': {x:555,y:115},
  'uz:theme/water': {x:875,y:175}, 'uz:theme/land-agriculture': {x:970,y:410},
  'uz:theme/forests-carbon': {x:760,y:600}, 'uz:theme/biodiversity': {x:390,y:600},
  'uz:theme/hazards-terrain': {x:170,y:410},
};
const conceptLayout = {
  'uz:analysis/change-over-time': {x:105,y:85}, 'uz:analysis/state-observation': {x:1080,y:85},
  'uz:analysis/risk-exposure': {x:1110,y:660}, 'uz:analysis/resource-system': {x:90,y:660},
  'uz:analysis/environmental-feature': {x:600,y:690},
};
const agentLabels = {
  'uz:agent/atlas-source':'atlas metadata', 'uz:agent/extraction-pipeline':'measured',
  'uz:agent/rule-lexical-v1':'rule', 'uz:agent/model-tfidf-knn-v1':'model',
  'uz:agent/curator':'curator', 'uz:agent/openstreetmap':'OpenStreetMap',
  'uz:agent/uzkad':'cadastre', 'uz:agent/uzhydromet':'Uzhydromet',
};
const flagLabels = {
  'extent-exceeds-uzbekistan':'Extent reaches beyond Uzbekistan',
  'crs-not-wgs84':'Not in WGS 84 — reproject before overlay',
  'attribute-encoding-cp1251':'Attributes need cp1251 decoding',
  'station-key-not-wmo-index':'Station keys do not match the climate series',
  'stations-missing-coordinates':'Some stations have no coordinates',
  'severe-class-imbalance':'Severe class imbalance',
  'licence-not-cleared-for-publication':'Licence not cleared for publication',
  'originating-agency-unconfirmed':'Originating agency unconfirmed',
  'may-contain-personal-data':'May contain personal data',
  'out-of-scope-for-the-portal':'Out of scope for the portal',
};
const prettyFlag = flag => flagLabels[flag] || flag.replaceAll('-',' ');

function OntologyExplorer({ onRequest }) {
  const [model,setModel] = useState(null);
  const [selectedId,setSelectedId] = useState(null);
  const [hoveredId,setHoveredId] = useState(null);
  const [query,setQuery] = useState('');
  const [activeDomain,setActiveDomain] = useState('All domains');
  const [zoom,setZoom] = useState(1);
  const [touring,setTouring] = useState(true);
  const [reducedMotion,setReducedMotion] = useState(false);
  useEffect(()=>{fetch('/data/ontology-graph.json').then(r=>r.json()).then(data=>{setModel(data);setSelectedId(data.datasets[0]?.id)})},[]);
  useEffect(()=>{
    const media=window.matchMedia('(prefers-reduced-motion: reduce)');
    const update=()=>{setReducedMotion(media.matches);if(media.matches)setTouring(false)};
    update(); media.addEventListener('change',update);
    return()=>media.removeEventListener('change',update);
  },[]);
  const labelOf=useMemo(()=>{
    const index={};
    if(model)['themes','analysis','properties','usecases','places'].forEach(scheme=>
      (model.vocabularies[scheme]||[]).forEach(concept=>{index[concept.id]=concept.prefLabel}));
    return id=>index[id]||id;
  },[model]);
  const ontologyDomains=useMemo(()=>(model?.vocabularies.themes||[])
    .filter(theme=>domainLayout[theme.id])
    .map(theme=>({id:theme.id,name:theme.prefLabel,color:theme.color,...domainLayout[theme.id]})),[model]);
  const graph = useMemo(()=>{
    const datasetNodes=[];
    ontologyDomains.forEach(domain=>{
      const items=(model?.datasets||[]).filter(item=>item.theme===domain.id);
      items.forEach((item,index)=>{
        const ring=Math.floor(index/10); const position=index%10; const count=Math.min(10,items.length-ring*10);
        const radius=54+ring*19; const angle=(position/Math.max(count,1))*Math.PI*2+(ring%2)*.27;
        datasetNodes.push({...item,title:item.label,category:domain.name,x:domain.x+Math.cos(angle)*radius,y:domain.y+Math.sin(angle)*radius,domain,concept:item.analysis});
      });
    });
    return datasetNodes;
  },[model,ontologyDomains]);
  const queryLower=query.trim().toLowerCase();
  const searchText=node=>[node.title,node.sourceTitle,node.category,labelOf(node.concept),
    ...node.observes.map(o=>labelOf(o.concept)),...node.useCases.map(labelOf)].join(' ').toLowerCase();
  const visibleNodes=useMemo(()=>graph.filter(node=>(activeDomain==='All domains'||node.category===activeDomain)&&(!queryLower||searchText(node).includes(queryLower))),[graph,activeDomain,queryLower]);
  const visibleIds=useMemo(()=>new Set(visibleNodes.map(node=>node.id)),[visibleNodes]);
  const isVisible=node=>visibleIds.has(node.id);
  const selected=graph.find(node=>node.id===selectedId);
  const focused=graph.find(node=>node.id===hoveredId)||selected;
  const focusedConcept=focused&&ontologyConcepts[focused.concept];
  const matchCount=visibleNodes.length;
  useEffect(()=>{
    if(!touring||reducedMotion||hoveredId||visibleNodes.length<2)return;
    const timer=window.setInterval(()=>setSelectedId(current=>{
      const index=visibleNodes.findIndex(node=>node.id===current);
      return visibleNodes[(index+1+visibleNodes.length)%visibleNodes.length].id;
    }),3600);
    return()=>window.clearInterval(timer);
  },[touring,reducedMotion,hoveredId,visibleNodes]);
  const selectNode=id=>{setSelectedId(id);setTouring(false)};
  const selectDomain=name=>{setActiveDomain(activeDomain===name?'All domains':name);setTouring(false)};
  return <section className="ontology" id="ontology"><div className="ontology-intro"><div><div className="kicker">03 / Catalog knowledge model</div><h2>From files to<br/><span>knowledge.</span></h2></div><p>The atlas catalogue is organized as connected records. Explore how every package belongs to an environmental domain and is associated with an analytical role.</p></div>
    <div className="ontology-toolbar"><div className="ontology-search"><Search size={17}/><input aria-label="Search ontology" value={query} onChange={e=>{setQuery(e.target.value);setTouring(false)}} placeholder="Find a dataset, domain or concept..."/><span>{matchCount} objects</span></div><div className="ontology-filters"><button aria-pressed={activeDomain==='All domains'} className={activeDomain==='All domains'?'active':''} onClick={()=>{setActiveDomain('All domains');setTouring(false)}}>All domains</button>{ontologyDomains.map(domain=><button aria-pressed={activeDomain===domain.name} key={domain.name} className={activeDomain===domain.name?'active':''} onClick={()=>selectDomain(domain.name)}><i style={{background:domain.color}}/>{domain.name}</button>)}</div></div>
    <div className="ontology-workspace"><div className={`ontology-canvas ${touring?'is-touring':''}`}><div className="ontology-controls"><button className={touring?'tour-active':''} onClick={()=>setTouring(value=>!value)} aria-label={touring?'Pause guided tour':'Play guided tour'} aria-pressed={touring}>{touring?<Pause/>:<Play/>}</button><button onClick={()=>setZoom(value=>Math.min(1.35,value+.1))} aria-label="Zoom in"><Plus/></button><button onClick={()=>setZoom(value=>Math.max(.72,value-.1))} aria-label="Zoom out"><Minus/></button><button onClick={()=>setZoom(1)} aria-label="Reset zoom"><RotateCcw/></button></div><div className="ontology-live"><i/><span>{touring?'GUIDED TOUR':'INTERACTIVE'}</span><b>{focused?.title||'CATALOG READY'}</b></div>
      <svg viewBox="0 0 1200 740" role="img" aria-label="Knowledge graph of Uzbekistan environmental datasets"><g style={{transform:`translate(600px, 370px) scale(${zoom}) translate(-600px, -370px)`,transformOrigin:'0 0'}}>
        <g className="ontology-core-links">{ontologyDomains.map(domain=><line key={domain.name} x1="600" y1="360" x2={domain.x} y2={domain.y}/>)}</g>
        <g className="ontology-data-links">{graph.map(node=><line key={node.id} x1={node.domain.x} y1={node.domain.y} x2={node.x} y2={node.y} style={{'--link-delay':`${(Number(node.id.split('-')[1])%16)*90}ms`}} className={`${isVisible(node)?'visible':'dim'} ${focused?.id===node.id?'focused-link':''} ${focused&&focused.category!==node.category?'context-dim':''}`}/>)}</g>
        {focused&&focusedConcept&&<line className="concept-link" x1={focused.x} y1={focused.y} x2={focusedConcept.x} y2={focusedConcept.y}/>}
        <g className="concept-nodes">{Object.entries(ontologyConcepts).map(([name,position])=><g key={name} transform={`translate(${position.x} ${position.y})`} className={focused?.concept===name?'related':''}><rect x="-53" y="-13" width="106" height="26"/><text>{name.toUpperCase()}</text></g>)}</g>
        <g className="root-node" transform="translate(600 360)"><circle className="root-halo" r="63"/><circle className="root-shell" r="49"/><circle className="root-core" r="38"/><Network size={25} x="-12.5" y="-23"/><text y="16">UZGEODATA</text><text className="root-subtitle" y="29">CATALOG MODEL</text></g>
        <g className="domain-nodes">{ontologyDomains.map((domain,index)=>{const count=graph.filter(node=>node.category===domain.name).length;const related=focused?.category===domain.name;return <g key={domain.name} transform={`translate(${domain.x} ${domain.y})`} className={`${activeDomain===domain.name?'selected-domain':''} ${related?'related-domain':''}`} onClick={()=>selectDomain(domain.name)}><circle className="domain-halo" r="42" style={{stroke:domain.color,'--domain-delay':`${index*.35}s`}}/><circle className="domain-shell" r="31" style={{stroke:domain.color}}/><circle className="domain-core" r="23"/><text y="-2">{domain.name.toUpperCase()}</text><text className="domain-count" y="12">{count} DATASETS</text></g>})}</g>
        <g className="dataset-nodes">{graph.map((node,index)=>{const focusedNode=focused?.id===node.id;return <g key={node.id} transform={`translate(${node.x} ${node.y})`} style={{'--node-delay':`${Math.min(index*12,900)}ms`}} className={`${isVisible(node)?'visible':'dim'} ${selectedId===node.id?'selected':''} ${focusedNode?'focused-node':''} ${focused&&focused.category===node.category?'related-node':''}`} onMouseEnter={()=>setHoveredId(node.id)} onMouseLeave={()=>setHoveredId(null)} onClick={()=>selectNode(node.id)}>{focusedNode&&<circle className="node-focus-ring" r="13"/>}<circle className="dataset-dot" r={selectedId===node.id?7:4} style={{fill:node.domain.color}}/><title>{node.title}</title></g>})}</g>
      </g></svg><div className="ontology-legend"><span><i className="legend-root"/>Atlas</span><span><i className="legend-domain"/>Domain</span><span><i className="legend-data"/>Dataset</span><span><i className="legend-concept"/>Analytical concept</span></div></div>
      <aside className="ontology-detail">{selected?<div className="entity-content" key={selected.id}><div className="entity-type"><span>DATASET ENTITY</span><small>{selected.id.toUpperCase()}</small></div><div className="entity-icon"><Network size={28}/></div><h3>{selected.title}</h3><p className="source-name">{selected.sourceTitle}</p><div className="relation-chain"><span>UZBEKISTAN ATLAS</span><b>→</b><span>{selected.category}</span><b>→</b><strong>{selected.concept}</strong></div><div className="entity-properties"><div><span>DOMAIN</span><strong>{selected.category}</strong></div><div><span>DESCRIBES</span><strong>{selected.concept}</strong></div><div><span>FORMAT</span><strong>{selected.extension}</strong></div><div><span>SOURCE SIZE</span><strong>{(selected.size/1024/1024).toFixed(selected.size>10*1024*1024?0:1)} MB</strong></div></div><div className="semantic-tags"><span>is a · Dataset</span><span>belongs to · {selected.category}</span><span>describes · {selected.concept}</span></div><button className="button" onClick={()=>onRequest(selected.title)}>Request this dataset <ArrowRight size={16}/></button></div>:<div className="entity-empty"><Network/><p>Select a node to inspect its relationships.</p></div>}</aside>
    </div>
  </section>
}

function Solutions({ onRequest }) {
  return <section className="section solutions" id="solutions">
    <div className="section-head inverted"><div><div className="kicker">04 / Decision applications</div><h2>One country.<br/><em>Many missions.</em></h2></div><p>UzGeoData is designed around decisions, not file formats. Each use case combines multiple atlas themes into a practical evidence base.</p></div>
    <div className="audience-strip"><span>BUILT FOR</span><strong>Government agencies</strong><strong>Regional planners</strong><strong>Research institutions</strong><strong>Engineering teams</strong><strong>Conservation organizations</strong></div>
    <div className="use-case-grid">{useCases.map(item => <article className="use-case-card" key={item.n}>
      <div className="case-top"><span>{item.n}</span><item.icon size={25}/><small>{item.sector}</small></div><h3>{item.title}</h3>
      <div className="case-question"><span>DECISION QUESTION</span><p>{item.question}</p></div><div className="case-outcome"><span>OPERATIONAL VALUE</span><p>{item.outcome}</p></div>
      <div className="case-data"><span>SUPPORTING DATA</span>{item.data.map(data=><b key={data}>{data}</b>)}</div><div className="case-users"><Building2 size={13}/>{item.users}</div>
      <button onClick={()=>onRequest(`${item.sector}: ${item.title}`)}>Discuss this use case <ArrowRight size={15}/></button>
    </article>)}</div>
    <div className="decision-flow"><div><div className="kicker">From question to evidence</div><h3>A clear path to usable data.</h3></div>{[['01','Discover','Search by theme, decision or place.'],['02','Inspect','Review coverage, relationships and source context.'],['03','Request','Confirm access, licensing and delivery needs.'],['04','Integrate','Use the data in GIS, research or planning workflows.']].map(step=><div className="flow-step" key={step[0]}><span>{step[0]}</span><strong>{step[1]}</strong><p>{step[2]}</p></div>)}</div>
  </section>
}

function TrustStrip() {
  return <section className="trust-strip" aria-label="Data principles"><span>SOURCE PRESERVING</span><span>•</span><span>STRUCTURED METADATA</span><span>•</span><span>LOCAL CONTEXT</span><span>•</span><span>WEB GIS READY</span><span>•</span><span>PROVENANCE AWARE</span></section>
}

function Community() {
  return <section className="community" id="community">
    <div className="community-image"><img src="/assets/field-team.png" alt="Uzbek geospatial field team in the mountains"/><span className="vertical-caption">Field intelligence / Tashkent Region</span></div>
    <div className="community-copy">
      <div className="kicker">05 / Community</div><h2>Data moves<br/>with people.</h2>
      <blockquote>“A useful spatial platform does more than publish files. It connects field knowledge, institutional memory and reproducible analysis.”</blockquote>
      <div className="quote-person"><div className="avatar">UZ</div><div><strong>UzGeoData principle</strong><span>Source titles remain visible with every catalog record</span></div></div>
      <div className="community-proof"><div><strong>134</strong><span>Environmental packages indexed</span></div><div><strong>7</strong><span>Environmental domains</span></div></div>
      <a href="#ontology">Explore the knowledge model <ArrowRight size={18}/></a>
    </div>
  </section>
}

function Standards() {
  return <section className="section standards" id="about">
    <div className="standards-copy"><div className="kicker">06 / Data discipline</div><h2>Know your<br/>source.</h2><p>Professional geodata is more than a file. The portal separates original source packages from optimized web derivatives and keeps access status visible.</p><a href="/relationships.html" className="button dark-button">Explore data relationships <ArrowRight size={17}/></a></div>
    <div className="standard-list">
      {[['01','Source-preserving workflow','Original ArcGIS packages remain separate from lightweight browser derivatives.'],['02','Machine-readable index','English titles, domains, source filenames and sizes are available as structured metadata.'],['03','Semantic organization','Catalog records are grouped by environmental domain and analytical role.'],['04','Explicit access status','Free, request-based, licensed and internal data are distinguished before delivery.']].map(x => <div className="standard-item" key={x[0]}><span>{x[0]}</span><div><h3>{x[1]}</h3><p>{x[2]}</p></div><Check size={20}/></div>)}
    </div>
  </section>
}

function CTA({ onAccess }) {
  return <section className="cta" id="join"><div className="cta-lines"/><div className="kicker">Start mapping</div><h2>Your next decision<br/>starts with better data.</h2><p>Tell us what you are building. We will help you find the right dataset, license and delivery format.</p><div><button className="button" onClick={onAccess}>Request data access <ArrowRight size={17}/></button><a href="mailto:hello@uzgeodata.uz">hello@uzgeodata.uz</a></div></section>
}

function Footer() {
  return <footer><div className="footer-top"><div><Logo/><p>Curated environmental geodata<br/>for a changing Uzbekistan.</p></div><div className="footer-links"><div><strong>EXPLORE</strong><a href="#catalog">Data catalog</a><a href="#solutions">Use cases</a><a href="#about">Methodology</a></div><div><strong>CONNECT</strong><a href="#community">Community</a><a href="mailto:hello@uzgeodata.uz">Contact</a><a href="#join">Data requests</a></div><div><strong>DATA</strong><a href="#about">Source policy</a><a href="#about">Access levels</a><a href="/admin">Admin access</a></div></div></div><div className="footer-bottom"><span>© 2026 UZGEODATA.UZ</span><span>BUILT IN UZBEKISTAN <span className="accent">●</span></span><span>41.3775° N / 64.5853° E</span></div></footer>
}

function AccessModal({ initial, onClose }) {
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const fn = event => event.key === 'Escape' && onClose();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', fn);
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', fn); };
  }, [onClose]);
  async function submit(event) {
    event.preventDefault(); setLoading(true); setError('');
    try {
      const response = await fetch('/api/requests', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))});
      const result = await response.json(); if (!response.ok) throw new Error(result.error); setDone(true);
    } catch (requestError) { setError(requestError.message); }
    finally { setLoading(false); }
  }
  return <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}><div className="modal" role="dialog" aria-modal="true" aria-labelledby="request-title">
    <button className="modal-close" onClick={onClose} aria-label="Close"><X/></button>
    {!done ? <><div className="kicker">Data request</div><h2 id="request-title">Let’s find your<br/><span>best source.</span></h2><p>Describe the decision or analysis you are supporting. Your request will be recorded for access and licensing review.</p><form onSubmit={submit}>
      <label>YOUR NAME<input name="name" required autoFocus placeholder="Full name"/></label><label>WORK EMAIL<input name="email" required type="email" placeholder="you@organization.uz"/></label><label>ORGANIZATION<input name="organization" placeholder="Agency, company or institution"/></label><label>DATASET OR TOPIC<input name="topic" required defaultValue={initial || ''} placeholder="e.g. flood risk, NDVI..."/></label><label>INTENDED USE<textarea name="intendedUse" rows="3" placeholder="Decision, study area, timeframe and preferred format"/></label>{error&&<div className="form-error" role="alert">{error}</div>}<button className="button" type="submit" disabled={loading}>{loading?<><LoaderCircle className="spin" size={17}/> Recording request…</>:<>Submit data request <ArrowRight size={17}/></>}</button>
    </form></> : <div className="success"><span><Check size={32}/></span><h2 id="request-title">Request recorded.</h2><p>Thank you. Your project context and dataset needs have been saved for review.</p><button className="button" onClick={onClose}>Back to the portal</button></div>}
  </div></div>
}

const fileSize = bytes => {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
};

function AdminLogin({ onLogin }) {
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function submit(event) {
    event.preventDefault(); setLoading(true); setError('');
    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch('/api/admin/login', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(Object.fromEntries(form)) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      onLogin();
    } catch (loginError) { setError(loginError.message); }
    finally { setLoading(false); }
  }
  return <div className="admin-shell login-shell"><div className="admin-logo"><Logo href="/"/></div><div className="login-card">
    <div className="login-mark"><LockKeyhole size={28}/></div><div className="kicker">Restricted system</div><h1>Admin<br/><span>access.</span></h1><p>Authorized UzGeoData personnel only. Sign in to manage the data repository.</p>
    <form onSubmit={submit}><label>USERNAME<input name="username" autoComplete="username" required autoFocus/></label><label>PASSWORD<input name="password" type="password" autoComplete="current-password" required/></label>{error && <div className="form-error">{error}</div>}<button className="button" disabled={loading}>{loading ? <LoaderCircle className="spin" size={18}/> : <>Enter repository <ArrowRight size={17}/></>}</button></form>
    <a href="/" className="back-link">← Back to public portal</a>
  </div><div className="login-image"/></div>
}

function AdminPanel() {
  const [authenticated, setAuthenticated] = useState(null);
  const [items, setItems] = useState([]);
  const [requests, setRequests] = useState([]);
  const [notice, setNotice] = useState('');
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState([]);
  useEffect(() => { document.title = 'Repository Administration — UzGeoData'; }, []);

  const load = async () => {
    const [dataResponse,requestResponse] = await Promise.all([fetch('/api/admin/datasets'),fetch('/api/admin/requests')]);
    if (dataResponse.status === 401 || requestResponse.status === 401) return setAuthenticated(false);
    setItems(await dataResponse.json()); setRequests(await requestResponse.json()); setAuthenticated(true);
  };
  useEffect(() => { fetch('/api/admin/session').then(r => r.json()).then(result => result.authenticated ? load() : setAuthenticated(false)).catch(() => setAuthenticated(false)); }, []);

  async function uploadDataset(event) {
    event.preventDefault(); setUploading(true); setNotice('');
    const form = event.currentTarget;
    try {
      const response = await fetch('/api/admin/datasets', { method: 'POST', body: new FormData(form) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      form.reset(); setSelected([]); setNotice(`“${result.title}” was uploaded successfully.`); await load();
    } catch (error) { setNotice(`Error: ${error.message}`); }
    finally { setUploading(false); }
  }

  async function remove(item) {
    if (!window.confirm(`Permanently remove “${item.title}” and its ${item.files.length} stored file(s)?`)) return;
    const response = await fetch(`/api/admin/datasets/${item.id}`, { method: 'DELETE' });
    if (response.ok) { setNotice(`“${item.title}” was removed.`); await load(); }
  }

  async function logout() { await fetch('/api/admin/logout', {method:'POST'}); setAuthenticated(false); }
  if (authenticated === null) return <div className="admin-loading"><LoaderCircle className="spin"/><span>Opening secure repository</span></div>;
  if (!authenticated) return <AdminLogin onLogin={load}/>;
  const totalBytes = items.flatMap(x => x.files).reduce((sum, file) => sum + file.size, 0);
  return <div className="admin-app">
    <header className="admin-header"><Logo href="/"/><div><span className="admin-status"><i/> Secure session</span><a href="/">View portal <ArrowRight size={15}/></a><button onClick={logout}><LogOut size={16}/> Sign out</button></div></header>
    <main className="admin-main"><div className="admin-title"><div><div className="kicker">Data operations</div><h1>Repository<br/><span>control.</span></h1></div><p>Upload, document and manage the files that power the UzGeoData catalog.</p></div>
      <div className="admin-stats"><div><Database/><span><strong>{items.length}</strong>Data entries</span></div><div><FileArchive/><span><strong>{items.reduce((sum,x)=>sum+x.files.length,0)}</strong>Stored files</span></div><div><HardDrive/><span><strong>{fileSize(totalBytes)}</strong>Total storage</span></div><div><Building2/><span><strong>{requests.length}</strong>Data requests</span></div></div>
      <div className="admin-grid"><section className="upload-panel"><div className="panel-heading"><span>01</span><div><h2>Upload data</h2><p>Add a complete dataset or supporting documentation.</p></div></div>
        <form onSubmit={uploadDataset}><label>DATASET TITLE<input name="title" required placeholder="e.g. Uzbekistan Atlas v2"/></label><div className="form-row"><label>DOMAIN<select name="category" required defaultValue=""><option value="" disabled>Select domain</option><option>Atlas</option><option>Climate</option><option>Infrastructure</option><option>Water</option><option>Land &amp; agriculture</option><option>Forests &amp; carbon</option><option>Biodiversity</option><option>Hazards &amp; terrain</option><option>Other</option></select></label><label>ACCESS LEVEL<select name="access" defaultValue="Request"><option>Free</option><option>Request</option><option>Licensed</option><option>Internal</option></select></label></div><label>DESCRIPTION<textarea name="description" rows="4" placeholder="Coverage, source, resolution and intended use..."/></label>
          <label className="drop-zone"><UploadCloud size={32}/><strong>Choose geodata files</strong><span>ZIP, SHP, GeoPackage, GeoTIFF, COG, GeoJSON, CSV, KML or PDF · up to 5 GB each</span><input type="file" name="files" multiple required onChange={e => setSelected([...e.target.files])}/></label>
          {selected.length > 0 && <div className="selected-files">{selected.map(file => <div key={`${file.name}-${file.size}`}><File size={15}/><span>{file.name}</span><small>{fileSize(file.size)}</small></div>)}</div>}
          {notice && <div className={notice.startsWith('Error') ? 'admin-notice error' : 'admin-notice'}>{notice}</div>}<button className="button" disabled={uploading}>{uploading ? <><LoaderCircle className="spin" size={18}/> Uploading…</> : <>Upload to repository <UploadCloud size={17}/></>}</button>
        </form></section>
        <section className="repository-panel"><div className="panel-heading"><span>02</span><div><h2>Stored data</h2><p>Private repository inventory.</p></div></div>
          <div className="repository-list">{items.length === 0 ? <div className="repository-empty"><Database size={35}/><h3>No uploads yet</h3><p>Your uploaded geodata will appear here.</p></div> : items.map(item => <article className="repository-item" key={item.id}><div className="repo-top"><span>{normalizeDomain(item.category)}</span><button onClick={() => remove(item)} title="Remove dataset"><Trash2 size={16}/></button></div><h3>{item.title}</h3><p>{item.description || 'No description provided.'}</p><div className="repo-meta"><span>{item.access}</span><span>{item.files.length} file{item.files.length === 1 ? '' : 's'}</span><span>{fileSize(item.files.reduce((sum,f)=>sum+f.size,0))}</span></div><div className="repo-files">{item.files.map(file => <a key={file.storedName} href={`/api/admin/datasets/${item.id}/files/${file.storedName}`}><File size={13}/>{file.originalName}</a>)}</div><time>{new Date(item.createdAt).toLocaleString()}</time></article>)}</div>
        </section></div>
      <section className="request-inbox"><div className="panel-heading"><span>03</span><div><h2>Access requests</h2><p>Project context submitted through the public portal.</p></div></div><div className="request-list">{requests.length===0?<div className="repository-empty"><Building2 size={34}/><h3>No requests yet</h3><p>Submitted data-access requests will appear here.</p></div>:requests.map(request=><article key={request.id}><div><span className="request-status">{request.status}</span><time>{new Date(request.createdAt).toLocaleString()}</time></div><h3>{request.topic}</h3><p>{request.intendedUse||'No intended use provided.'}</p><div className="request-contact"><span><strong>{request.name}</strong>{request.organization&&` · ${request.organization}`}</span><a href={`mailto:${request.email}?subject=${encodeURIComponent(`UzGeoData request: ${request.topic}`)}`}>{request.email} <ArrowRight size={13}/></a></div></article>)}</div></section>
    </main>
  </div>;
}

function PublicPortal() {
  const [request, setRequest] = useState(null);
  const openRequest = (dataset = '') => setRequest(dataset || 'General data request');
  return <><Header onAccess={() => openRequest()}/><main><Hero onExplore={() => document.getElementById('catalog').scrollIntoView({behavior:'smooth'})} onAccess={() => openRequest()}/><Catalog onRequest={openRequest}/><EnvironmentalMap/><OntologyExplorer onRequest={openRequest}/><Solutions onRequest={openRequest}/><TrustStrip/><Community/><Standards/><CTA onAccess={() => openRequest()}/></main><Footer/>{request !== null && <AccessModal initial={request} onClose={() => setRequest(null)}/>}</>;
}

export default function App() {
  return window.location.pathname.startsWith('/admin') ? <AdminPanel/> : <PublicPortal/>;
}
