import { useEffect, useMemo, useState } from 'react';
import {
  ArrowDown, ArrowRight, Check, Database, Droplets, FileArchive, Grid3X3,
  Layers3, Leaf, Menu, Mountain, Orbit, Search, X
} from 'lucide-react';

const datasets = [
  { title: 'Uzbekistan Atlas v1', category: 'Atlas', type: 'SHP', size: '1.8 GB', access: 'Free', icon: Mountain, desc: 'Administrative, terrain, transport and settlement layers digitized from the first national atlas.' },
  { title: 'Uzbekistan Atlas v2', category: 'Atlas', type: 'GPKG', size: '3.2 GB', access: 'Request', icon: Layers3, desc: 'Expanded thematic collection with standardized topology, metadata and projection references.' },
  { title: 'National Water Network', category: 'Water', type: 'SHP', size: '486 MB', access: 'Free', icon: Droplets, desc: 'Rivers, canals, reservoirs, basins and hydraulic structures for planning and research.' },
  { title: 'Land Cover Mosaic 2025', category: 'Raster', type: 'COG', size: '14.6 GB', access: 'Request', icon: Grid3X3, desc: 'Cloud-minimized multispectral land-cover mosaic, analysis-ready and tiled for web access.' },
  { title: 'Agricultural Parcels', category: 'Agriculture', type: 'GPKG', size: '2.4 GB', access: 'Licensed', icon: Leaf, desc: 'Field boundaries and crop classification for national agricultural monitoring workflows.' },
  { title: 'Digital Elevation Model', category: 'Terrain', type: 'GeoTIFF', size: '8.1 GB', access: 'Free', icon: Orbit, desc: 'Nationwide 30 m elevation surface with derived slope, aspect and hillshade products.' },
];

const goals = [
  { n: '01', title: 'Water management', icon: Droplets, copy: 'Model watersheds, trace canal networks and monitor change across the Aral Sea basin.', tags: ['Hydrology', 'Infrastructure', 'Climate'] },
  { n: '02', title: 'Agriculture', icon: Leaf, copy: 'Turn land-cover, soil and parcel layers into decisions for more resilient production.', tags: ['Crop health', 'Land use', 'Irrigation'] },
  { n: '03', title: 'Research', icon: Orbit, copy: 'Build reproducible analysis with cited, versioned and interoperable source material.', tags: ['Academia', 'Remote sensing', 'Open science'] },
];

function Logo({ light = false }) {
  return <a href="#top" className="logo" aria-label="UzGeoData home">
    <svg viewBox="0 0 38 38" aria-hidden="true"><path d="M5 7h8v15c0 5 2 8 6 8s6-3 6-8V7h8v16c0 9-5 14-14 14S5 32 5 23V7Z"/><path className="logo-bar" d="M13 2h21v5H13z"/></svg>
    <span>UZ<span className="accent">GEO</span>DATA</span>
  </a>
}

function Header({ onAccess }) {
  const [open, setOpen] = useState(false);
  return <header className="site-header">
    <Logo />
    <button className="menu-button" onClick={() => setOpen(!open)} aria-label="Toggle menu">{open ? <X/> : <Menu/>}</button>
    <nav className={open ? 'open' : ''} onClick={() => setOpen(false)}>
      <a href="#catalog">Data catalog</a><a href="#solutions">Use cases</a><a href="#community">Community</a><a href="#about">About</a>
    </nav>
    <button className="button button-small desktop-cta" onClick={onAccess}>Request access <ArrowRight size={16}/></button>
  </header>
}

function Hero({ onExplore, onAccess }) {
  return <section className="hero" id="top">
    <div className="hero-image" />
    <div className="hero-grid" />
    <div className="hero-content">
      <div className="eyebrow"><span className="pulse"/> Uzbekistan’s geospatial data infrastructure</div>
      <h1>Map what<br/><span>matters.</span></h1>
      <p className="hero-copy">Authoritative geodata for the people shaping Uzbekistan. Atlas vectors, analysis-ready rasters and specialist datasets—organized, documented and ready to work.</p>
      <div className="hero-actions">
        <button className="button" onClick={onExplore}>Explore data <ArrowDown size={17}/></button>
        <button className="text-button" onClick={onAccess}>Request a dataset <ArrowRight size={17}/></button>
      </div>
    </div>
    <div className="hero-stats">
      <div><strong>240<span>+</span></strong><small>Verified datasets</small></div>
      <div><strong>14</strong><small>Administrative regions</small></div>
      <div><strong>22<span>TB</span></strong><small>Raster coverage</small></div>
    </div>
    <div className="coordinates">41.3775° N&nbsp;&nbsp;&nbsp; 64.5853° E</div>
    <div className="scroll-note"><span>Scroll to discover</span><ArrowDown size={14}/></div>
  </section>
}

function Catalog({ onRequest }) {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState('All data');
  const categories = ['All data', 'Atlas', 'Water', 'Raster', 'Agriculture', 'Terrain'];
  const shown = useMemo(() => datasets.filter(d => (active === 'All data' || d.category === active) && (`${d.title} ${d.desc} ${d.type}`).toLowerCase().includes(query.toLowerCase())), [query, active]);
  return <section className="section catalog-section" id="catalog">
    <div className="section-head">
      <div><div className="kicker">01 / Data catalog</div><h2>Built for real<br/>decisions.</h2></div>
      <p>From original atlas sheets to current earth observation products. Every dataset is quality-checked, documented and delivered in formats your tools understand.</p>
    </div>
    <div className="catalog-tools">
      <div className="search-box"><Search size={20}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search datasets, formats or themes..."/><span>{shown.length} results</span></div>
      <div className="filters">{categories.map(c => <button className={active === c ? 'active' : ''} onClick={() => setActive(c)} key={c}>{c}</button>)}</div>
    </div>
    <div className="dataset-grid">
      {shown.map((d, i) => <article className="dataset-card" key={d.title} style={{'--delay': `${i * 45}ms`}}>
        <div className="dataset-top"><span className="data-icon"><d.icon size={22}/></span><span className={`access ${d.access.toLowerCase()}`}>{d.access}</span></div>
        <div className="dataset-code">UZG / {String(i + 1).padStart(3,'0')} · {d.category.toUpperCase()}</div>
        <h3>{d.title}</h3><p>{d.desc}</p>
        <div className="dataset-meta"><span><FileArchive size={15}/>{d.type}</span><span><Database size={15}/>{d.size}</span></div>
        <button onClick={() => onRequest(d.title)}>{d.access === 'Free' ? 'View & download' : 'Request access'} <ArrowRight size={17}/></button>
      </article>)}
      {shown.length === 0 && <div className="empty-state"><Search size={30}/><h3>No exact match</h3><p>Try a broader theme or clear your filters.</p><button onClick={() => {setQuery(''); setActive('All data')}}>Clear search</button></div>}
    </div>
    <a href="#catalog" className="catalog-link">Browse all 240 datasets <ArrowRight size={18}/></a>
  </section>
}

function Solutions() {
  return <section className="section solutions" id="solutions">
    <div className="section-head inverted"><div><div className="kicker">02 / Use cases</div><h2>One country.<br/><em>Many missions.</em></h2></div><p>Find the right layers for the work ahead. Our collections are organized around Uzbekistan’s most urgent priorities.</p></div>
    <div className="goal-grid">{goals.map((g, i) => <article className="goal-card" key={g.n}>
      <div className="goal-orbit"><g.icon size={30}/></div><span className="goal-number">{g.n}</span><h3>{g.title}</h3><p>{g.copy}</p>
      <div className="goal-tags">{g.tags.map(t => <span key={t}>{t}</span>)}</div><a href="#catalog">View collection <ArrowRight size={16}/></a>
    </article>)}</div>
  </section>
}

function TrustStrip() {
  return <section className="trust-strip"><span>OPEN STANDARDS</span><span>•</span><span>VERIFIED METADATA</span><span>•</span><span>LOCAL EXPERTISE</span><span>•</span><span>QGIS READY</span><span>•</span><span>VERSION CONTROLLED</span></section>
}

function Community() {
  return <section className="community" id="community">
    <div className="community-image"><img src="/assets/field-team.png" alt="Uzbek geospatial field team in the mountains"/><span className="vertical-caption">Field intelligence / Tashkent Region</span></div>
    <div className="community-copy">
      <div className="kicker">03 / Community</div><h2>Data moves<br/>with people.</h2>
      <blockquote>“We mapped 1,200 km of irrigation channels in weeks, not months. For the first time, every team was working from the same truth.”</blockquote>
      <div className="quote-person"><div className="avatar">AM</div><div><strong>Aziza M.</strong><span>Water systems researcher, Tashkent</span></div></div>
      <div className="community-proof"><div><strong>1,800+</strong><span>Researchers, planners & builders</span></div><div><strong>38</strong><span>Partner institutions</span></div></div>
      <a href="#join">Join the community <ArrowRight size={18}/></a>
    </div>
  </section>
}

function Standards() {
  return <section className="section standards" id="about">
    <div className="standards-copy"><div className="kicker">04 / The standard</div><h2>Know your<br/>source.</h2><p>Professional geodata is more than a file. We preserve provenance, document every transformation and publish clear usage rights.</p><a href="#catalog" className="button dark-button">Read our methodology <ArrowRight size={17}/></a></div>
    <div className="standard-list">
      {[['01','Traceable provenance','Source sheets, acquisition dates and processing history included.'],['02','Interoperable formats','GeoPackage, Shapefile, GeoTIFF, COG and web services.'],['03','Human quality control','Reviewed by local specialists who understand the landscape.'],['04','Clear licensing','Know what is open, attributed or licensed before you download.']].map(x => <div className="standard-item" key={x[0]}><span>{x[0]}</span><div><h3>{x[1]}</h3><p>{x[2]}</p></div><Check size={20}/></div>)}
    </div>
  </section>
}

function CTA({ onAccess }) {
  return <section className="cta" id="join"><div className="cta-lines"/><div className="kicker">Start mapping</div><h2>Your next decision<br/>starts with better data.</h2><p>Tell us what you are building. We will help you find the right dataset, license and delivery format.</p><div><button className="button" onClick={onAccess}>Request data access <ArrowRight size={17}/></button><a href="mailto:hello@uzgeodata.uz">hello@uzgeodata.uz</a></div></section>
}

function Footer() {
  return <footer><div className="footer-top"><div><Logo/><p>Authoritative geospatial data<br/>for a changing Uzbekistan.</p></div><div className="footer-links"><div><strong>EXPLORE</strong><a href="#catalog">Data catalog</a><a href="#solutions">Use cases</a><a href="#about">Methodology</a></div><div><strong>CONNECT</strong><a href="#community">Community</a><a href="mailto:hello@uzgeodata.uz">Contact</a><a href="#join">Partners</a></div><div><strong>LEGAL</strong><a href="#about">Licensing</a><a href="#about">Terms</a><a href="#about">Privacy</a></div></div></div><div className="footer-bottom"><span>© 2026 UZGEODATA.UZ</span><span>BUILT IN UZBEKISTAN <span className="accent">●</span></span><span>41.3775° N / 64.5853° E</span></div></footer>
}

function AccessModal({ initial, onClose }) {
  const [done, setDone] = useState(false);
  useEffect(() => { const fn = e => e.key === 'Escape' && onClose(); document.addEventListener('keydown', fn); return () => document.removeEventListener('keydown', fn) }, [onClose]);
  return <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}><div className="modal">
    <button className="modal-close" onClick={onClose} aria-label="Close"><X/></button>
    {!done ? <><div className="kicker">Data request</div><h2>Let’s find your<br/><span>best source.</span></h2><p>Tell us what you need. Our data team typically responds within one working day.</p><form onSubmit={e => {e.preventDefault(); setDone(true)}}>
      <label>YOUR NAME<input required placeholder="Full name"/></label><label>WORK EMAIL<input required type="email" placeholder="you@organization.uz"/></label><label>DATASET OR TOPIC<input required defaultValue={initial || ''} placeholder="e.g. Atlas v2, hydrology..."/></label><label>HOW WILL YOU USE IT?<textarea rows="3" placeholder="A short description of your project"/></label><button className="button" type="submit">Send request <ArrowRight size={17}/></button>
    </form></> : <div className="success"><span><Check size={32}/></span><h2>Request received.</h2><p>Thank you. We’ll review your needs and reply within one working day.</p><button className="button" onClick={onClose}>Back to the portal</button></div>}
  </div></div>
}

export default function App() {
  const [request, setRequest] = useState(null);
  const openRequest = (dataset = '') => setRequest(dataset || 'General data request');
  return <><Header onAccess={() => openRequest()}/><main><Hero onExplore={() => document.getElementById('catalog').scrollIntoView({behavior:'smooth'})} onAccess={() => openRequest()}/><Catalog onRequest={openRequest}/><Solutions/><TrustStrip/><Community/><Standards/><CTA onAccess={() => openRequest()}/></main><Footer/>{request !== null && <AccessModal initial={request} onClose={() => setRequest(null)}/>}</>;
}
