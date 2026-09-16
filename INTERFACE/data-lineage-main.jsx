import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Check, ExternalLink, HardDrive, Search } from 'lucide-react';
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

function NodeIcon({ kind }) {
  if (kind === 'satellite') return <><rect x="-7" y="-5" width="14" height="10" rx="2"/><path d="M-8 0h-10M8 0h10M-18-6v12M18-6v12M-13-6v12M13-6v12M-3-8l4-5"/></>;
  if (kind === 'station') return <><path d="M0-13L-9 11M0-13l9 24M-6 3H6M-8 9H8M0-13v24"/><circle cx="0" cy="-14" r="2.5"/></>;
  if (kind === 'water') return <><path d="M-14-4c5-5 9 5 14 0s9 5 14 0M-14 3c5-5 9 5 14 0s9 5 14 0M-14 10c5-5 9 5 14 0s9 5 14 0"/></>;
  if (kind === 'land') return <><path d="M-15 10L-4-5 3 3 9-8 16 10z"/><path d="M-8 10l5-8 4 5"/></>;
  if (kind === 'vegetation') return <><path d="M-2 12C-2-4 5-12 14-13c0 11-5 19-16 19M-3 13C-4 1-9-6-15-8c-1 9 3 15 12 15M-2 12l10-18"/></>;
  if (kind === 'ice') return <><path d="M-16 11L-3-12 4-2 9-9 17 11z"/><path d="M-9 0l6-12 4 6 3 4 5-7"/></>;
  if (kind === 'lake') return <><ellipse cx="0" cy="2" rx="16" ry="8"/><path d="M-12 1c5-3 8 3 13 0s8 3 12 0"/></>;
  if (kind === 'gauge') return <><path d="M-14 8c5-5 9 5 14 0s9 5 14 0M-9-10v13M9-10v13M-9-10H9M0-10V3"/><circle cx="0" cy="-4" r="3"/></>;
  if (kind === 'atlas') return <><ellipse cx="0" cy="-8" rx="13" ry="5"/><path d="M-13-8v16c0 3 6 5 13 5s13-2 13-5V-8M-13 0c0 3 6 5 13 5S13 3 13 0"/></>;
  if (kind === 'model') return <><circle cx="0" cy="0" r="5"/><circle cx="0" cy="0" r="13"/><path d="M-18 0h10M8 0h10M0-18v10M0 8v10"/></>;
  return <circle cx="0" cy="0" r="10"/>;
}

function TaxonomyNode({ x, y, label, detail, branch, kind, tier = 'leaf', selected, onSelect }) {
  const activate = () => onSelect(branch);
  return <g className={`taxonomy-node taxonomy-${tier} branch-${branch} ${selected === branch ? 'active' : ''}`} transform={`translate(${x} ${y})`}
    role="button" tabIndex="0" aria-label={`${label}. Show ${branch.replaceAll('_', ' ')} sources`}
    onClick={activate} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); } }}>
    <circle className="node-halo" r={tier === 'major' ? 27 : 21}/><g className="node-icon"><NodeIcon kind={kind}/></g>
    <text className="node-label" x={tier === 'major' ? 38 : 30} y={detail ? -3 : 4}>{label}</text>
    {detail && <text className="node-detail" x={tier === 'major' ? 38 : 30} y="14">{detail}</text>}
  </g>;
}

function LineageTree({ lineage, selected, onSelect }) {
  const choose = id => { onSelect(id); document.querySelector('.registry-toolbar')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); };
  const count = id => lineage.branches.find(branch => branch.id === id)?.items.length || 0;
  return <figure className="taxonomy-figure">
    <figcaption><span>UZGEODATA DATA ECOSYSTEM</span><strong>Observation systems branch into environmental evidence and derived basin products.</strong></figcaption>
    <div className="taxonomy-scroll">
      <svg className="taxonomy-tree" viewBox="0 0 1100 770" role="img" aria-labelledby="taxonomy-title taxonomy-desc">
        <title id="taxonomy-title">UzGeoData scientific data source tree</title>
        <desc id="taxonomy-desc">A branching taxonomy from the UzGeoData evidence root to satellite and gridded observations, ground observations, reference atlases, research datasets and recomputed outputs. Leaves include water, land, vegetation, glaciers, lakes, climate and discharge.</desc>
        <g className="taxonomy-structure">
          <path className="trunk" d="M96 617C165 617 173 555 214 500C258 441 252 337 320 286"/>
          <path className="edge earth_engine" d="M214 500C248 401 249 226 334 154"/>
          <path className="edge local" d="M214 500C266 500 288 496 342 496"/>
          <path className="edge downloads" d="M153 586C247 620 285 655 356 661"/>
          <path className="edge derived" d="M138 610C259 704 397 726 553 720"/>

          <path className="edge earth_engine thin" d="M355 154C445 154 451 81 530 79"/>
          <path className="edge earth_engine thin" d="M355 154C445 154 457 203 530 203"/>
          <path className="edge earth_engine thin" d="M355 154C426 154 453 333 530 333"/>
          <path className="edge earth_engine twig" d="M552 79C643 79 659 43 750 43M552 79C642 79 665 84 750 84M552 79C643 79 659 125 750 125"/>
          <path className="edge earth_engine twig" d="M552 203C647 203 661 176 750 176M552 203C647 203 661 217 750 217M552 203C647 203 661 258 750 258"/>
          <path className="edge earth_engine twig" d="M552 333C641 333 665 309 750 309M552 333C645 333 663 350 750 350M552 333C644 333 663 391 750 391"/>

          <path className="edge local thin" d="M364 496C445 496 458 457 532 457M364 496C448 496 459 520 532 520M364 496C439 496 459 583 532 583"/>
          <path className="edge local twig" d="M554 457C657 457 674 441 782 441M554 457C658 457 675 477 782 477"/>
          <path className="edge local twig" d="M554 520C660 520 674 513 782 513M554 520C659 520 674 549 782 549"/>
          <path className="edge external twig" d="M554 583C650 583 675 585 782 585"/>

          <path className="edge downloads thin" d="M378 661C468 661 482 637 558 637M378 661C468 661 482 678 558 678"/>
          <path className="edge downloads twig" d="M580 637C665 637 688 622 782 622M580 678C666 678 689 662 782 662"/>
          <path className="edge derived thin" d="M575 720C663 720 683 705 782 705M575 720C665 720 684 741 782 741"/>
        </g>

        <TaxonomyNode x={96} y={617} label="UzGeoData" detail="evidence root" branch="earth_engine" kind="model" tier="root" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={334} y={154} label="Satellite & gridded" detail={`${count('earth_engine')} assessed sources`} branch="earth_engine" kind="satellite" tier="major" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={530} y={79} label="Climate & water balance" detail="models + reanalysis" branch="earth_engine" kind="water" tier="domain" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={530} y={203} label="Land & ecosystems" detail="surface observation" branch="earth_engine" kind="vegetation" tier="domain" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={530} y={333} label="Cryosphere & surface water" detail="optical inventories" branch="earth_engine" kind="ice" tier="domain" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={750} y={43} label="Precipitation · ET" detail="TerraClimate / CHIRPS" branch="earth_engine" kind="water" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={750} y={84} label="Temperature · drought" detail="ERA5-Land / TerraClimate" branch="earth_engine" kind="land" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={750} y={125} label="Runoff · soil water" detail="modelled basin state" branch="earth_engine" kind="water" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={750} y={176} label="Land cover" detail="Copernicus / Dynamic World" branch="earth_engine" kind="land" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={750} y={217} label="Vegetation · biomes" detail="ecoregions + potential cover" branch="earth_engine" kind="vegetation" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={750} y={258} label="Soils · human footprint" detail="OpenLandMap / GHSL" branch="earth_engine" kind="land" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={750} y={309} label="Snow cover · SWE" detail="MODIS + modelled pack" branch="earth_engine" kind="ice" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={750} y={350} label="Glaciers" detail="GLIMS inventories" branch="earth_engine" kind="ice" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={750} y={391} label="Lakes · surface water" detail="JRC / HydroLAKES" branch="earth_engine" kind="lake" selected={selected} onSelect={choose}/>

        <TaxonomyNode x={342} y={496} label="Ground observations" detail={`${count('local')} local/provider sources`} branch="local" kind="station" tier="major" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={532} y={457} label="Hydrological gauges" detail="river + reservoir records" branch="local" kind="gauge" tier="domain" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={532} y={520} label="Weather stations" detail="point observations" branch="local" kind="station" tier="domain" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={532} y={583} label="Research archives" detail="published station datasets" branch="external" kind="atlas" tier="domain" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={782} y={441} label="Discharge" detail="daily + monthly flow" branch="local" kind="water" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={782} y={477} label="Water level · storage" detail="gauge or operator delivery" branch="local" kind="lake" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={782} y={513} label="Rain · air temperature" detail="Pskem / Oygaing / Tashkent" branch="local" kind="station" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={782} y={549} label="Field inventories" detail="glaciers · lakes · dams" branch="local" kind="ice" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={782} y={585} label="CA-discharge" detail="297 gauges · integrated" branch="external" kind="gauge" selected={selected} onSelect={choose}/>

        <TaxonomyNode x={356} y={661} label="Reference sources" detail={`${count('downloads')} download candidates`} branch="downloads" kind="atlas" tier="major" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={558} y={637} label="Hydrography" detail="basins · rivers · lakes" branch="downloads" kind="water" tier="domain" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={558} y={678} label="Terrain & land" detail="elevation · soils · ecology" branch="downloads" kind="land" tier="domain" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={782} y={622} label="Basin topology" detail="HydroSHEDS / BasinATLAS" branch="downloads" kind="water" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={782} y={662} label="Static reference layers" detail="fixed or versioned editions" branch="downloads" kind="atlas" selected={selected} onSelect={choose}/>

        <TaxonomyNode x={553} y={720} label="Recomputed products" detail={`${count('derived')} update groups`} branch="derived" kind="model" tier="major" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={782} y={705} label="Basin time series" detail="observations · anomalies" branch="derived" kind="water" selected={selected} onSelect={choose}/>
        <TaxonomyNode x={782} y={741} label="Indicators · case studies" detail="versioned analytical outputs" branch="derived" kind="model" selected={selected} onSelect={choose}/>
      </svg>
    </div>
    <div className="taxonomy-legend" aria-label="Source tree legend">
      <button className={selected === 'earth_engine' ? 'active' : ''} onClick={() => choose('earth_engine')}><i className="earth_engine"/>Satellite & gridded</button>
      <button className={selected === 'local' ? 'active' : ''} onClick={() => choose('local')}><i className="local"/>Ground observations</button>
      <button className={selected === 'downloads' ? 'active' : ''} onClick={() => choose('downloads')}><i className="downloads"/>Reference sources</button>
      <button className={selected === 'external' ? 'active' : ''} onClick={() => choose('external')}><i className="external"/>Research datasets</button>
      <button className={selected === 'derived' ? 'active' : ''} onClick={() => choose('derived')}><i className="derived"/>Recomputed outputs</button>
    </div>
  </figure>;
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
      <section id="tree"><div className="section-head"><div><p className="eyebrow">01 / THE SOURCE TREE</p><h2>From observation systems to environmental evidence.</h2></div><p>Read the tree from its root to the major observation limbs, environmental domains and measured variables. Select any limb or leaf to filter the detailed source registry below.</p></div>
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
      <section className="ca-data"><p className="eyebrow">04 / INTEGRATED RESEARCH DATASET</p><h2>CA-discharge is now integrated as a research archive beside ground observation.</h2><p>The versioned release holds 297 gauge locations and time series for 136 gauges—published with a 24.6 MB GeoPackage in the research index. It serves as station evidence, a gauge crosswalk and regional validation candidate. The 11.8 GB raw-data archive remains external; the compact compiled data and consistency checks are public.</p><div className="ca-actions"><a href="https://www.nature.com/articles/s41597-023-02474-8" target="_blank" rel="noreferrer">Read the paper <ExternalLink size={14}/></a><a href="https://doi.org/10.5281/zenodo.8147591" target="_blank" rel="noreferrer">Open the Zenodo record <ExternalLink size={14}/></a><a href="/data/research/ca-discharge-summary.json" target="_blank" rel="noreferrer">View the summary <ExternalLink size={14}/></a></div><details><summary>Integration details</summary><ul><li><strong>Stations:</strong> 297 gauge locations in 8 Central Asian countries (95 Uzbekistan)</li><li><strong>Time series:</strong> 136 series with observations; 244,632 records from 1910–2021</li><li><strong>Quality control:</strong> Glacier-thinning attributes excluded per original publisher warnings</li><li><strong>Pskem validation:</strong> 555 paired dekads compared to local station; Pearson r = 0.98</li><li><strong>Coverage:</strong> Evidence registers in the research index; GeoPackage archived outside the website</li></ul></details></section>
      <footer>Registry assembled from the live Earth Engine audit, generated variable inventory and curated source classifications · updated {bundle.registry.updated_at} · <a href="/data/source-registry.json">Download registry JSON</a></footer>
    </>}
  </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
