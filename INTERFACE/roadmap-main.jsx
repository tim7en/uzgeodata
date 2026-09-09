import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import AtlasProcessing from './AtlasProcessing.jsx';
import PskemAtlasBatch from './PskemAtlasBatch.jsx';
import './roadmap.css';

function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const [year, setYear] = useState(2026);
  const [checked, setChecked] = useState('');
  async function refresh() {
    try {
      const response = await fetch('/data/atlas/roadmap.json', { cache: 'no-store' });
      if (!response.ok) throw new Error(`Roadmap request failed (${response.status})`);
      const next = await response.json();
      if (!Array.isArray(next.attributes) || !Array.isArray(next.phases)) throw new Error('Invalid roadmap data');
      setData(next); setError(''); setChecked(new Date().toLocaleTimeString());
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { refresh(); const timer = setInterval(refresh, 60000); return () => clearInterval(timer); }, []);
  const rows = data?.attributes.filter(a => (category === 'all' || a.category === category)
    && `${a.column} ${a.label} ${a.variable}`.toLowerCase().includes(query.toLowerCase())) || [];
  return <main>
    <nav><a href="/">UzGeoData / Basins</a><a href="/atlas.html">Atlas explorer ↗</a></nav>
    <header className="hero"><p className="eyebrow">THE ATLAS PROGRAMME · AMU DARYA + SYR DARYA</p>
      <h1>From basin attributes<br/>to a living atlas.</h1>
      <p>A shared roadmap for source methods, reproducible science and basin history. Starting with HydroSHEDS.</p>
      <div className="refresh"><button onClick={refresh}>Refresh updates</button><span>Checks every 60 seconds{checked && ` · Last checked ${checked}`}</span></div>
    </header>
    {error && <p role="alert">{error}. {data ? 'Showing the last successful response.' : 'Use Refresh updates to retry.'}</p>}
    {!data && !error && <p role="status">Loading the atlas programme…</p>}
    {data && <>
      <div className="metrics"><div><strong>{data.counts.specified}</strong><span>attribute methods specified</span></div><div><strong>{data.counts.implemented}</strong><span>recipes implemented in this module</span></div><div><strong>{data.counts.reproduced}</strong><span>independently reproduced</span></div><div><strong>2000–26</strong><span>historical planning window</span></div></div>
      <PskemAtlasBatch/>
      <details><summary>Earlier single-attribute pilot runs</summary><AtlasProcessing/></details>
      <section><div className="section-heading"><h2>The roadmap</h2><span>Evidence-based gates · status as of {data.as_of}</span></div>
        <div className="phases">{data.phases.map((phase, i) => <article className={`phase ${phase.status}`} key={phase.id} id={phase.id}>
          <div className="phase-top"><span className="number">{String(i + 1).padStart(2, '0')}</span><span className="badge">{phase.status.replaceAll('_', ' ')}</span></div>
          <h3>{phase.title}</h3><p>{phase.description}</p><details><summary>Acceptance gate & dependencies</summary><p>{phase.gate}</p><p>Depends on: {phase.depends_on.length ? phase.depends_on.map(id => data.phases.find(p => p.id === id)?.title).join(', ') : 'No preceding phase'}</p>{phase.evidence.map(e => <p key={e}>Evidence: <code>{e}</code></p>)}</details>
        </article>)}</div>
      </section>
      <div className="two-columns"><section><h2>Atlas modules</h2>{data.modules.map(m => <article className="module" key={m.id}><span className="badge">{m.status}</span><h3>{m.title}</h3><p>{m.scope}</p><p>{m.attribute_count} attributes · v{m.version}</p><strong>Scientific reproduction required</strong></article>)}<p>Each future thematic atlas gets its own sources, functions and validation package under the shared scientific contract.</p></section>
      <section><h2>Project updates & source news</h2>{data.updates.map(u => <article className="update" key={u.id}><small>{u.date} · {u.kind.replaceAll('_', ' ')}</small><h3>{u.title}</h3><p>{u.summary}</p><a href={`#${u.phase}`}>Affected phase</a>{u.source.startsWith('https://') ? <a href={u.source} target="_blank" rel="noreferrer">Source ↗</a> : <p className="path">{u.source}</p>}</article>)}<small>Curated project feed. External news is added with a dated source after review.</small></section></div>
      <section className="history"><h2>History without invented observations</h2><p>Choose a planning year. Static layers and climatologies retain their original periods; annual extensions need verified source coverage. Full-year 2026 is still provisional.</p>
        <label>Planning year <select value={year} onChange={e => setYear(Number(e.target.value))}>{data.years.map(y => <option key={y}>{y}</option>)}</select></label>
        <div className="years" aria-label="Historical planning years">{data.years.map(y => <button key={y} className={y === year ? 'selected' : ''} onClick={() => setYear(y)} aria-pressed={y === year}>{y}</button>)}</div>
        <p><strong>{year}: no annual observations generated by this module.</strong> Static pilot computations retain their reference period. The policies below identify what must be assessed before annual basin values can be stored.</p><a href="/data/atlas/history-plan.csv" download>Download the 2000–2026 planning ledger ↓</a>
      </section>
      <section><div className="section-heading"><h2>Attribute method library</h2><span>{rows.length} of {data.attributes.length} attributes</span></div>
        <div className="filters"><label>Find an attribute<input value={query} onChange={e => setQuery(e.target.value)} placeholder="Snow, elevation, dis_m3_pyr…"/></label><label>Theme<select value={category} onChange={e => setCategory(e.target.value)}><option value="all">All themes</option>{[...new Set(data.attributes.map(a => a.category))].sort().map(c => <option key={c}>{c}</option>)}</select></label></div>
        <div className="attributes">{rows.map(a => { const fn = data.functions.find(f => f.id === a.function); return <details key={a.id}><summary><code>{a.column}</code><span>{a.label}</span><small>{a.annual_policy.replaceAll('_', ' ')}</small></summary><div className="recipe"><p><strong>{fn.source.dataset}</strong> · {fn.source.citation} · <a href={a.source_url} target="_blank" rel="noreferrer">Catalogue page {fn.source.page} ↗</a></p><p>{fn.steps}</p><pre>{a.pseudocode}</pre><p>Reference period: {a.reference_period} · Units: {a.units}</p><p>{year} policy: {a.annual_policy.replaceAll('_', ' ')}. Availability has not been verified; no value is implied.</p><p>Before implementation: {fn.review_gates.join('; ')}.</p><p>Ontology: <code>{a.ontology_concept}</code> — semantic mapping requires review.</p></div></details>; })}</div>
        {!rows.length && <p>No matching attributes. Clear the search or change the theme.</p>}
      </section>
      <section className="contract"><h2>Reproduction is a release requirement.</h2><p>Every result needs pinned inputs, a versioned method, execution records, declared tolerances, comparison against the reference and an independent rerun.</p><div className="downloads"><a href="/data/atlas/reproducibility.md" download>Scientific requirements ↓</a><a href="/data/atlas/methodology.md" download>Methodology ↓</a><a href="/data/atlas/recipes.md" download>All attribute pseudocode ↓</a><a href="/data/atlas/roadmap.json" download>Machine-readable specification ↓</a></div></section>
      <footer>Specification v{data.version} · {data.refresh_policy}</footer>
    </>}
  </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
