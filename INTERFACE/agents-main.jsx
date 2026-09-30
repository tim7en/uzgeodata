import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './agents.css';
import { onLocalServer } from './localServer.js';

const BASE = import.meta.env.BASE_URL;
const FALLBACK = `${BASE}data/agent-status.json`;
const TERMINAL = new Set(['succeeded', 'failed', 'interrupted']);
function when(value) { return value ? new Date(value).toLocaleString() : 'Not yet run'; }

function App() {
  const [snapshot, setSnapshot] = useState(null);
  const [reviewed, setReviewed] = useState(null);
  const [local, setLocal] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  useEffect(() => {
    let alive = true, timer = null, connected = false;
    // The reviewed snapshot is always shown; its findings and statuses are what was published.
    fetch(FALLBACK).then(response => {
      if (!response.ok) throw Error('Status snapshot unavailable');
      return response.json();
    }).then(data => { if (alive) setReviewed(data); }).catch(cause => { if (alive) setError(cause.message); });
    async function refresh() {
      if (!onLocalServer()) return;
      try {
        const response = await fetch('/api/agents', { cache: 'no-store' });
        if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw Error('No local runner');
        const data = await response.json();
        connected = true;
        if (alive) { setSnapshot(data); setLocal(true); timer = setTimeout(refresh, 2500); }
      } catch {
        // The public site has no runner: stop asking rather than polling a 404 forever.
        // A runner that was reachable may be restarting, so keep trying it.
        if (!alive) return;
        if (connected) timer = setTimeout(refresh, 5000);
        else setLocal(false);
      }
    }
    refresh();
    return () => { alive = false; clearTimeout(timer); };
  }, []);
  async function run(id) {
    setError('');
    try {
      const response = await fetch(`/api/agents/${encodeURIComponent(id)}/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      const result = await response.json();
      if (!response.ok) throw Error(result.error || `Request failed (${response.status})`);
      setSelected(result.id);
    } catch (cause) { setError(cause.message); }
  }
  const jobs = snapshot?.jobs || [];
  const checks = (local ? snapshot : reviewed)?.checks || [];
  const published = id => reviewed?.checks?.find(check => check.id === id);
  return <div className="agents-page">
    <header><a className="brand" href="/">UZGEODATA <span>/ Scientific QA</span></a><nav><a href="/">Portal</a><a href="/data-lineage.html">Data lineage</a><a href="/admin.html">Data freshness</a></nav></header>
    <main>
      <div className="eyebrow">Research control room</div><h1>Validation agents</h1>
      <p className="intro">Recalculate selected portal claims and inspect their evidence. A successful run verifies only the stated sample and method. Findings that need review remain visible.</p>
      <div className={`mode ${local ? 'local' : 'public'}`}><strong>{local ? 'Private local runner connected' : 'Public reviewed snapshot'}</strong><span>{local ? 'Runs execute one at a time on this computer. Output and history stay in WORKSPACE/agent-runs.' : `Reviewed ${when(reviewed?.reviewed_at)}${reviewed?.atlas_release ? ` against atlas release ${reviewed.atlas_release}` : ''}. Reruns are available from the local operator server.`}</span></div>
      {error && <p role="alert" className="error">{error}</p>}
      <section className="grid" aria-label="Validation agents">{checks.map(check => {
        const job = jobs.find(item => item.check_id === check.id);
        const status = local ? job?.status || 'not run' : check.status;
        const review = published(check.id);
        return <article key={check.id} className="card"><div className="card-head"><h2>{check.label}</h2><span className={`status ${status?.toLowerCase()}`}>{status}</span></div>
          <p>{check.description}</p><div className="card-foot"><small>{local ? `${when(job?.finished_at || job?.started_at)}${review ? ` · last reviewed: ${review.status}` : ''}` : check.summary}</small>{local && <button disabled={job && !TERMINAL.has(job.status)} onClick={() => run(check.id)}>{job && !TERMINAL.has(job.status) ? 'Running…' : 'Rerun'}</button>}</div>
          {local && job && <button className="log-link" onClick={() => setSelected(selected === job.id ? null : job.id)}>{selected === job.id ? 'Hide run log' : 'View run log'}</button>}
          {local && selected === job?.id && <pre>{job.log || job.message}</pre>}
        </article>;
      })}</section>
      <section className="findings"><h2>What the current evidence says</h2><ul>
        {(reviewed?.findings || []).map(item => <li key={item.title}><strong>{item.title}:</strong> {item.text}</li>)}
      </ul><p>Scientific review and source files: <a href="https://github.com/tim7en/uzgeodata/tree/main/qa/deep_dive">QA evidence</a>. Local reruns do not automatically change the public snapshot.</p></section>
    </main>
  </div>;
}
createRoot(document.getElementById('root')).render(<App/>);
