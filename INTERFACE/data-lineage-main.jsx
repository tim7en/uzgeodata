import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowRight, Check, Database, Download, ExternalLink, GitBranch, HardDrive, RefreshCw, Satellite, Search } from 'lucide-react';
import './data-lineage.css';
import ThemeToggle, { initTheme } from './ThemeToggle.jsx';
import LanguageSelect from './LanguageSelect.jsx';
import { initLang } from './lang.js';
import { autoHideHeader } from './chrome.js';
import { buildLineage, filterItems, shortDate } from './sourceLineageModel.js';
initTheme();
initLang();

const loadJson = async url => {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) throw Error(`${url} returned ${response.status}`);
  return response.json();
};
const labels = {
  continuous_collection: 'Continuing collection', versioned_release: 'Versioned release',
  fixed_reference: 'Fixed reference', local_snapshot: 'Local snapshot', derived_product: 'Derived product',
};
const cadence = days => days ? (days < 45 ? 'Monthly' : days < 370 ? 'Annual' : `Every ${days} days`) : 'On demand';

function LineageTree({ lineage, selected, onSelect }) {
  const icons = { earth_engine: Satellite, local: HardDrive, downloads: Download, external: Database, derived: RefreshCw };
  return <div className="tree-shell">
    <div className="tree-root"><GitBranch/><span><small>LINEAGE ROOT</small><strong>UzGeoData evidence</strong></span></div>
    <ul className="tree-branches" aria-label="Data lineage branches">{lineage.branches.map(branch => {
      const Icon = icons[branch.id];
      return <li key={branch.id}><button className={selected === branch.id ? 'selected' : ''} onClick={() => onSelect(branch.id)} aria-pressed={selected === branch.id}>
        <Icon/><span><strong>{branch.label}</strong><small>{branch.items.length} sources · {branch.note}</small></span><ArrowRight/>
      </button></li>;
    })}</ul>
  </div>;
}

function SourceCard({ item }) {
  const families = item.families || [];
  const variables = item.variables || [];
  const state = item.comparison === 'source_newer' ? 'New source periods available'
    : item.comparison === 'aligned' ? 'Published record aligned' : item.state || 'Classified source';
  return <article className="source-card">
    <div className="card-top"><span className={`class-pill ${item.classification}`}>{labels[item.classification] || item.classification}</span><span className={`state ${item.comparison || ''}`}>{state}</span></div>
    <h3>{item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.title} <ExternalLink size={13}/></a> : item.title}</h3>
    <p className="source-id">{item.asset || item.provider || item.id}</p>
    {item.sourceLatest && <div className="dates"><span><small>Source catalogue latest</small><strong>{shortDate(item.sourceLatest)}</strong></span><span><small>UzGeoData dated record</small><strong>{item.publishedTo || 'Not published'}</strong></span></div>}
    {item.coverage && <p><strong>Coverage:</strong> {item.coverage}</p>}
    {item.update_policy && <p><strong>Update rule:</strong> {item.update_policy}</p>}
    {item.note && <p>{item.note}</p>}
    {item.storage_note && <p className="storage-note"><HardDrive size={15}/>{item.storage_note}</p>}
    {item.intervalDays && <p><strong>Target cadence:</strong> {cadence(item.intervalDays)}</p>}
    {!!families.length && <details><summary>{families.length} variable {families.length === 1 ? 'family' : 'families'}</summary><ul>{families.map(family => <li key={`${item.id}:${family.id}`}><code>{family.id}</code> {family.label}<small>{family.category} · used: {family.usedPeriod}</small></li>)}</ul></details>}
    {!!variables.length && <details><summary>{variables.length} {typeof variables[0] === 'string' ? 'included variables' : 'published variables'}</summary><ul>{variables.slice(0, 24).map((variable, index) => typeof variable === 'string' ? <li key={variable}>{variable}</li> : <li key={variable.id || index}>{variable.label}<small>{variable.coverage_to ? `through ${variable.coverage_to}` : variable.status}</small></li>)}</ul>{variables.length > 24 && <p>Plus {variables.length - 24} more variables in the inventory.</p>}</details>}
    {item.article_url && <div className="external-links"><a href={item.article_url} target="_blank" rel="noreferrer">Paper <ExternalLink size={12}/></a><a href={item.data_url} target="_blank" rel="noreferrer">Data record <ExternalLink size={12}/></a></div>}
  </article>;
}

function App() {
  const navRef = useRef(null);
  const [bundle, setBundle] = useState(null), [error, setError] = useState('');
  const [branchId, setBranchId] = useState('earth_engine'), [query, setQuery] = useState(''), [classification, setClassification] = useState('all');
  const load = () => {
    setError('');
    Promise.all([loadJson('/data/atlas/dynamic-atlas.json'), loadJson('/data/variable-inventory.json'), loadJson('/data/source-registry.json')])
      .then(([dynamicAtlas, inventory, registry]) => setBundle({ dynamicAtlas, inventory, registry, lineage: buildLineage(dynamicAtlas, inventory, registry) }))
      .catch(nextError => setError(nextError.message));
  };
  useEffect(load, []);
  useEffect(() => autoHideHeader(navRef.current), []);
  const branch = bundle?.lineage.branches.find(item => item.id === branchId);
  const visible = useMemo(() => filterItems(branch?.items || [], query, classification), [branch, query, classification]);
  return <main>
    <nav ref={navRef}><a href="/">← UzGeoData</a><div><a href="/catalogue.html">Catalogue</a><a href="/dynamic-atlas.html">Methods</a><a href="/admin.html">Update console</a><ThemeToggle/><LanguageSelect style={{display:'inline-flex'}}/></div></nav>
    <header><p className="eyebrow">SOURCE REGISTRY / LINEAGE / UPDATE READINESS</p><h1>Know what exists.<br/><em>Know what can move.</em></h1><p className="intro">A source tree for the data we reference, fetch, store and recompute. Dates are separated into provider availability, UzGeoData coverage and fixed scientific periods so a saved 2024 endpoint is never mistaken for one universal cutoff.</p><div className="hero-links"><a href="#tree">Explore the source tree ↓</a><a href="#update-system">See the update system ↓</a></div></header>
    {error ? <div className="error" role="alert"><p>Could not assemble the registry: {error}</p><button onClick={load}>Retry</button></div> : !bundle ? <p role="status">Classifying sources and building lineage…</p> : <>
      <section className="cutoff"><div><p className="eyebrow">WHY DOES 2024 APPEAR?</p><h2>It means three different things.</h2></div><div className="cutoff-grid"><article><strong>1</strong><h3>Provider limit</h3><p>The live audit finds TerraClimate ending at December 2024. Here, 2024 really is the latest catalogue period currently observed.</p></article><article><strong>2</strong><h3>Saved extraction window</h3><p>MODIS snow has 2026 imagery, but some published records and the case-study run stop in 2024. Those can be extended and recomputed.</p></article><article><strong>3</strong><h3>Local delivery</h3><p>Pskem station workbooks end in 2024. Earth Engine cannot extend a local gauge record; a new provider delivery is required.</p></article></div></section>
      <div className="metrics"><div><strong>{bundle.lineage.counts.sources}</strong><span>classified source or process nodes</span></div><div><strong>{bundle.lineage.counts.continuing}</strong><span>continuing Earth Engine collections</span></div><div><strong>{bundle.lineage.counts.sourceNewer}</strong><span>sources newer than our dated record</span></div><div><strong>{bundle.lineage.counts.updateGroups}</strong><span>existing recomputation groups</span></div></div>
      <section id="tree"><div className="section-head"><div><p className="eyebrow">01 / THE SOURCE TREE</p><h2>From upstream evidence to published variables.</h2></div><p>Select a branch to inspect its sources. Each leaf states whether it is a continuing collection, a fixed or versioned reference, a local snapshot, or a product we recompute.</p></div>
        <LineageTree lineage={bundle.lineage} selected={branchId} onSelect={id => { setBranchId(id); setQuery(''); setClassification('all'); }}/>
        <div className="registry-toolbar"><label><Search size={16}/>Search this branch<input value={query} onChange={event => setQuery(event.target.value)} placeholder="source, variable, asset…"/></label><label>Temporal class<select value={classification} onChange={event => setClassification(event.target.value)}><option value="all">All classes</option>{bundle.registry.classification.map(item => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label></div>
        <p className="result-count" aria-live="polite">{visible.length} of {branch.items.length} nodes in {branch.label}</p>
        <div className="source-grid">{visible.map(item => <SourceCard item={item} key={`${branch.id}:${item.id}`}/>)}</div>
      </section>
      <section className="classification"><div><p className="eyebrow">02 / CLASSIFICATION CONTRACT</p><h2>Update behaviour belongs in the metadata.</h2><p>“Latest” is only meaningful once the temporal class is known. A monthly satellite collection, a land-cover release and a station spreadsheet cannot share one refresh rule.</p></div><div>{bundle.registry.classification.map(item => <article key={item.id}><span className={`class-dot ${item.id}`}/><div><h3>{item.label}</h3><p>{item.meaning}</p></div></article>)}</div></section>
      <section id="update-system"><div className="section-head"><div><p className="eyebrow">03 / UPDATE SYSTEM</p><h2>The pipeline exists. Scheduling is the missing layer.</h2></div><p>The repository already has source audits, incremental extractors, validation metadata and update groups. The public site is static, so unattended refreshes still need a credentialled runner, storage and publication approval.</p></div>
        <div className="update-flow">{[
          ['01','Discover','Audit provider dates and compare them with the last approved coverage.','Implemented'],
          ['02','Fetch','Download only missing periods into versioned raw or observation storage.','Implemented for core regional groups'],
          ['03','Validate','Check completeness, units, masks and revisions; recompute dependent basin variables.','Partly implemented'],
          ['04','Approve','Publish a new immutable release and retain the previous scientific snapshot.','Implemented; currently manual'],
          ['05','Schedule','Run by source cadence, alert on failure and monitor disk use.','Still required'],
        ].map(([number,title,copy,state]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{copy}</p><small><Check size={12}/>{state}</small></article>)}</div>
        <div className="system-note"><div><h3>Recommended operating rule</h3><p>Poll monthly collections monthly, but publish only complete periods after QA. Check versioned releases quarterly. Never overwrite a case-study snapshot: extend it as a new run and keep the old inputs addressable.</p></div><div><h3>Storage rule</h3><p>Keep raw rasters outside the website artifact. Publish basin aggregates, manifests and checksums here. Large future variables belong in expandable object storage with a local cache, not GitHub Pages.</p></div></div>
      </section>
      <section className="ca-data"><p className="eyebrow">04 / PROPOSED EXTERNAL DATASET</p><h2>CA-discharge belongs beside the satellite tree—not underneath it.</h2><p>The linked dataset is a versioned research release with 295 gauge locations and time series for 135 gauges. It is valuable as station evidence, a crosswalk and a regional validation or modelling input. It is not a live satellite feed and should not be silently merged into satellite-derived runoff.</p><div className="ca-actions"><a href="https://www.nature.com/articles/s41597-023-02474-8" target="_blank" rel="noreferrer">Read the paper <ExternalLink size={14}/></a><a href="https://doi.org/10.5281/zenodo.8147591" target="_blank" rel="noreferrer">Open the Zenodo record <ExternalLink size={14}/></a></div><ol><li>Reserve versioned raw storage and record the release checksum.</li><li>Crosswalk gauge coordinates and identifiers without replacing local station identities.</li><li>Import its daily, 10-day and monthly series with original quality flags.</li><li>Validate overlaps before using it for model training or claims of independent performance.</li></ol></section>
      <footer>Registry assembled from the live Earth Engine audit, generated variable inventory and curated source classifications · updated {bundle.registry.updated_at} · <a href="/data/source-registry.json">Download registry JSON</a></footer>
    </>}
  </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
