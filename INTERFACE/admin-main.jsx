import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ArrowLeft, ArrowUpRight, Check, Clock, Database, Layers, LoaderCircle, RefreshCw, Search, ShieldCheck, X } from 'lucide-react';
import { LAYERS, freshness, coverageAge, visibleRows, latestJob } from './variableFreshness.js';
import './admin.css';
import { initTheme } from './ThemeToggle.jsx';
import { initLang, mountSelect } from './lang.js';
import { autoHideHeader } from './chrome.js';

initTheme();
initLang();

const BASE = import.meta.env.BASE_URL;
async function json(url, options) {
  const response = await fetch(url, { cache: 'no-store', ...options });
  if (!response.headers.get('content-type')?.includes('application/json')) throw Error('This host serves the saved inventory. Update controls need the admin server.');
  const result = await response.json();
  if (!response.ok) throw Error(result.error || `Request failed (${response.status})`);
  return result;
}
const stamp = value => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : 'Not recorded';
const ageText = age => age === null ? '' : age < 1 ? 'Less than a day ago' : `${Math.floor(age)} days ago`;

function Freshness({ row, now }) {
  const f = freshness(row, now);
  return <div className={`freshness ${f.state}`}>
    <div className="freshness-value"><span>{f.label}</span><strong>{f.score === null ? '—' : `${f.score}%`}</strong></div>
    <div className="freshness-track" role="meter" aria-label={`${row.label} update freshness`} aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={f.score ?? undefined} aria-valuetext={f.score === null ? f.label : `${f.score}% freshness`}><i style={{ width: `${f.score ?? 0}%` }}/></div>
    <small>{row.interval_days ? `${row.interval_days}-day update interval` : 'No automatic expiry'}</small>
  </div>;
}

function Admin() {
  const [data, setData] = useState(null), [server, setServer] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState('');
  const [now, setNow] = useState(Date.now()), [query, setQuery] = useState(''), [layer, setLayer] = useState('all');
  const [status, setStatus] = useState('all'), [collection, setCollection] = useState('all'), [page, setPage] = useState(0), [selected, setSelected] = useState(null);
  const [groupsOpen, setGroupsOpen] = useState(false);
  async function load(live = server) {
    try {
      const result = await json(live ? '/api/admin/variables' : `${BASE}data/variable-inventory.json`);
      setData(result); setError(''); setNow(Date.now());
    } catch (e) { setError(e.message); }
  }
  useEffect(() => {
    // The static site has no server: fall back to the published snapshot.
    json('/api/admin/variables').then(result => { setServer(true); setData(result); setNow(Date.now()); }).catch(() => { setServer(false); load(false); });
  }, []);
  useEffect(() => { const timer = setInterval(() => { setNow(Date.now()); if (server) load(true); }, 5000); return () => clearInterval(timer); }, [server]);
  useEffect(() => setPage(0), [query, layer, status, collection]);
  const rows = data?.rows || [], operations = data?.operations;
  const groups = operations?.groups || data?.groups || [];
  const filtered = useMemo(() => visibleRows(rows, { query, layer, status, collection }, now), [rows, query, layer, status, collection, now]);
  const counts = { total: rows.length, due: rows.filter(row => freshness(row, now).state === 'overdue').length,
    unknown: rows.filter(row => ['unknown', 'missing'].includes(freshness(row, now).state)).length,
    coverage: rows.filter(row => coverageAge(row, now)?.behind).length };
  const currentPage = Math.min(page, Math.max(0, Math.ceil(filtered.length / 40) - 1));

  async function action(id, days) {
    setBusy(id); setNotice(''); setError('');
    try {
      await json(days === undefined ? '/api/admin/variables/update' : '/api/admin/variables/schedule', {
        method: days === undefined ? 'POST' : 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_id: id, ...(days === undefined ? {} : { days }) }),
      });
      setNotice(days === undefined ? 'Update queued. Its progress appears below.' : days ? 'Automatic updates enabled while the admin server is running.' : 'Automatic updates turned off.');
      await load(true);
    } catch (e) { setError(e.message); } finally { setBusy(''); }
  }

  return <div className="admin-page">
    <header className="admin-topbar"><a className="admin-brand" href={BASE}><span className="brand-icon"><Layers size={21}/></span>UZGEODATA <span className="admin-badge">ADMIN</span></a>
      <div><a href={BASE}><ArrowLeft size={14}/> Back to map</a></div></header>
    <main>
      <div className="admin-heading"><div><p className="eyebrow">DATA OPERATIONS</p><h1>Know how current<br/>your data is.</h1><p className="heading-description">Every registered variable, its latest update, and the next action.<br/>One place to maintain the environmental record.</p></div>
        <div className="inventory-stamp"><span className={`connection-dot ${server ? 'connected' : ''}`}/><b>{server ? 'Update server connected' : 'Published snapshot'}</b><p>Inventory generated<br/>{stamp(data?.generated_at)}</p><button className="secondary" onClick={() => load()}><RefreshCw size={14}/> Refresh status</button></div></div>

      {error && <div className="message error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError('')}><X size={16}/></button></div>}
      {notice && <div className="message notice" role="status"><Check size={16}/>{notice}</div>}
      <div className="admin-summary">
        {[['Registered products', counts.total, 'Across four analytical layers', Database], ['Update due', counts.due, 'Past the expected update interval', Clock], ['Older data coverage', counts.coverage, 'Last observation needs attention', Activity], ['Missing / unknown', counts.unknown, 'Date, policy or data not recorded', Search]].map(([label, value, detail, Icon]) => <article key={label}><div><span>{label}</span><Icon size={17}/></div><strong>{value.toLocaleString()}</strong><small>{detail}</small></article>)}
      </div>

      <div className="operations-note"><ShieldCheck size={20}/><div><strong>{server ? 'Updates are managed on this server' : 'This is the published inventory snapshot.'}</strong><p>{server ? 'Jobs run one at a time. Automatic schedules persist across restarts and run while the server is online. Local changes need a separate deployment to reach the public site.' : 'Run npm run admin on a machine with the data to update freshness. Results appear here after the next release.'}</p></div><button className="text-button" onClick={() => setGroupsOpen(!groupsOpen)}>{groupsOpen ? 'Hide' : 'Manage'} update groups</button></div>
      {groupsOpen && <section className="group-panel" aria-label="Update groups"><h2>Update groups</h2><p>Related variables update together. A schedule applies to the entire group.</p><div className="group-list">{groups.map(group => {
        const schedule = operations?.schedules?.[group.id];
        const job = latestJob(operations?.jobs, group.id); const active = ['queued', 'running'].includes(job?.status);
        return <article key={group.id}><div><strong>{group.label}</strong><small>{rows.filter(row => row.group_id === group.id).length} products · {group.note}</small>{server && <small>{group.mode === 'full-refresh' ? 'Full refresh: rebuilds dependent atlas products.' : group.mode === 'published-append' ? 'Limited append: history and cube only; climatologies, basin API, coverage ledger and release stay unchanged.' : 'Runs the registered pipeline steps.'} Local inputs checked; Python and provider access are checked when the job starts.</small>}{group.reason && <p className="prerequisite">{group.reason}</p>}{schedule?.next_run && <small>Next: {stamp(schedule.next_run)}</small>}{schedule?.error && <p className="prerequisite">{schedule.error}</p>}</div>
          <label>Keep updated<select aria-label={`Schedule ${group.label}`} value={schedule?.days || 0} disabled={!server || busy === group.id} onChange={e => action(group.id, Number(e.target.value))}><option value={0}>Off</option><option value={1}>Daily</option><option value={7}>Weekly</option><option value={30}>Every 30 days</option></select></label>
          <button className="primary" disabled={!server || active || busy === group.id || group.ready === false} onClick={() => action(group.id)}>{active ? <LoaderCircle size={14} className="spin"/> : <RefreshCw size={14}/>} {active ? job.status : 'Update group'}</button></article>;
      })}</div></section>}

      {!!operations?.jobs?.length && <section className="job-list" aria-label="Recent update jobs"><h2>Recent updates</h2>{operations.jobs.slice(0, 4).map(job => <article key={job.id}><div><b>{job.label}</b><span className={`job-status ${job.status}`}>{job.status}</span><small>{stamp(job.finished_at || job.started_at || job.created_at)}</small></div><p>{job.message}</p><progress aria-label={`${job.label} job progress`} max="100" value={job.progress}/></article>)}</section>}

      <section className="inventory-section"><div className="inventory-title"><h2>Variable inventory <span>{rows.length}</span></h2><p>Freshness: <i className="legend-dot green"/> recent <i className="legend-dot amber"/> aging <i className="legend-dot red"/> due</p></div>
        <div className="layer-tabs" aria-label="Analytical layers"><button className={layer === 'all' ? 'active' : ''} onClick={() => setLayer('all')}>All layers</button>{Object.entries(LAYERS).map(([id, label]) => <button key={id} className={layer === id ? 'active' : ''} onClick={() => setLayer(id)}><span>{id}</span>{label}</button>)}</div>
        <div className="inventory-filters"><label className="search-field"><Search size={17}/><input aria-label="Search variables" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search variable, source or product ID…"/></label>
          <select aria-label="Filter collection" value={collection} onChange={e => setCollection(e.target.value)}><option value="all">All collections</option>{[...new Set(rows.map(row => row.collection))].sort().map(name => <option key={name}>{name}</option>)}</select>
          <select aria-label="Filter freshness" value={status} onChange={e => setStatus(e.target.value)}><option value="all">All statuses</option><option value="attention">Needs attention</option><option value="fresh">Recently updated</option><option value="overdue">Update due</option><option value="unknown">Unknown</option><option value="missing">Missing</option><option value="reference">Reference / historical</option></select></div>
        <p className="score-explanation">100% immediately after an update → 0% when the expected interval elapses. This measures update age, not download completion or scientific quality. Fixed references and unknown dates have no score.</p>
        {!data && !error ? <div className="empty"><LoaderCircle className="spin"/> Loading inventory…</div> : <div className="inventory-table-wrap"><table><thead><tr><th>Variable / product</th><th>Layer</th><th>Update freshness</th><th>Last updated <small>Your local time</small></th><th>Data covers through</th><th>Action</th></tr></thead><tbody>{filtered.slice(currentPage * 40, currentPage * 40 + 40).map(row => {
          const f = freshness(row, now), coverage = coverageAge(row, now), group = groups.find(g => g.id === row.group_id);
          const job = latestJob(operations?.jobs, row.group_id); const active = ['queued', 'running'].includes(job?.status);
          return <tr key={row.id}><td><button className="variable-name" onClick={() => setSelected(row)}>{row.label}</button><small className="variable-source">{row.collection}</small><code>{row.id}</code></td><td><span className={`layer-tag layer-${row.layer}`}>{row.layer} · {LAYERS[row.layer]}</span></td>
            <td><Freshness row={row} now={now}/></td><td><time>{stamp(row.last_updated)}</time><small>{ageText(f.age)}</small></td><td><span>{row.coverage_to || row.coverage_label || 'Fixed / unspecified period'}</span>{coverage?.behind && <small className="coverage-warning">{coverage.label}</small>}</td><td>{group && server && group.ready !== false ? <button className="row-update" disabled={active || busy === group.id} onClick={() => action(group.id)}><RefreshCw size={13} className={active ? 'spin' : ''}/>{active ? `${job.progress}%` : 'Update group'}</button>
              : <button className="row-details" onClick={() => setSelected(row)}>{group ? server ? 'Setup needed' : 'View update options' : 'View details'}<ArrowUpRight size={13}/></button>}</td></tr>;
        })}</tbody></table>{data && !filtered.length && <div className="empty">No variables match these filters.<button onClick={() => { setQuery(''); setLayer('all'); setStatus('all'); setCollection('all'); }}>Clear filters</button></div>}</div>}
        <div className="pagination"><span>{filtered.length ? `${currentPage * 40 + 1}–${Math.min((currentPage + 1) * 40, filtered.length)} of ${filtered.length}` : '0 results'}</span><div><button disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>Previous</button><button disabled={(currentPage + 1) * 40 >= filtered.length} onClick={() => setPage(currentPage + 1)}>Next</button></div></div>
      </section>
      <footer className="admin-footer"><span>UzGeoData · Data operations</span><span>Reference → Observations → Analytical products → Models</span></footer>
    </main>
    {selected && <div className="modal-backdrop"><section className="admin-dialog details-dialog" role="dialog" aria-modal="true" aria-labelledby="details-title"><button className="dialog-close" aria-label="Close details" onClick={() => setSelected(null)}><X/></button><span className="eyebrow">PRODUCT DETAILS · LAYER {selected.layer}</span><h2 id="details-title">{selected.label}</h2><code>{selected.id}</code><p>{selected.note}</p><dl><dt>Source</dt><dd>{selected.source || 'Not registered'}</dd><dt>Unit</dt><dd>{selected.unit || 'See source metadata'}</dd><dt>Last updated</dt><dd>{stamp(selected.last_updated)}<small>{selected.updated_basis}</small></dd><dt>Data coverage</dt><dd>{selected.coverage_to || selected.coverage_label || 'See reference source period'}</dd></dl>
      {selected.group_id ? <><h3>Update this source group</h3><p>{groups.find(g => g.id === selected.group_id)?.label} · {rows.filter(r => r.group_id === selected.group_id).length} products update together.</p><p className="prerequisite">{groups.find(g => g.id === selected.group_id)?.reason}</p><button className="primary" onClick={() => { setSelected(null); setGroupsOpen(true); }}>{server ? 'Manage update group' : 'View setup and schedule options'}</button></> : <><h3>{selected.status === 'on_demand' ? 'Computed when requested' : 'Manual source review'}</h3><p>{selected.status === 'on_demand' ? 'Use the Python analytical API against a named data release.' : 'No automatic update is registered for this product. Add a reviewed provider recipe or import a new source edition before enabling updates.'}</p>{selected.manual_command && <><p>Existing maintenance command (run in the pipeline environment):</p><pre>{selected.manual_command}</pre></>}</>}
      {selected.evidence && <a className="evidence-link" href={selected.evidence} target="_blank" rel="noreferrer">Open source metadata <ArrowUpRight size={14}/></a>}</section></div>}
  </div>;
}

createRoot(document.getElementById('root')).render(<Admin/>);
requestAnimationFrame(() => {
  autoHideHeader(document.querySelector('.admin-topbar'));
  const tools = document.querySelector('.admin-topbar > div');
  if (tools) {
    const host = document.createElement('span');
    tools.insertBefore(host, tools.firstChild);
    mountSelect(host);
  }
});
