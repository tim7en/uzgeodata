import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDown, ArrowUp, Database, Download, Filter, LoaderCircle,
  Network, Search, Table2, Waves, X,
} from 'lucide-react';

const TRIPLES_URL = '/data/ontology-triples.json';
const FEATURES_URL = '/data/hydrography/relationships.json';
const PAGE = 200;

function num(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return Number(value).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Literals are strings, numbers, bboxes and intervals; all have to read as text. */
function literal(value) {
  if (value === null || value === undefined) return '';
  if (Array.isArray(value)) return value.map(v => (typeof v === 'number' ? v.toFixed(3) : v)).join(', ');
  if (typeof value === 'object') return Object.entries(value).map(([k, v]) => `${k}: ${v}`).join(', ');
  return String(value);
}

function shortId(id) {
  if (!id) return '';
  const slash = id.indexOf('/');
  return slash < 0 ? id : id.slice(slash + 1);
}

function download(filename, rows, columns) {
  const escape = cell => {
    const text = cell === null || cell === undefined ? '' : String(cell);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const body = [
    columns.map(column => escape(column.label)).join(','),
    ...rows.map(row => columns.map(column => escape(column.csv(row))).join(',')),
  ].join('\n');
  const url = URL.createObjectURL(new Blob([`﻿${body}`], { type: 'text/csv;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** Sorting, paging and export are the same job for every table here. */
function useTable(rows, columns, initialSort) {
  const [sort, setSort] = useState(initialSort);
  const [limit, setLimit] = useState(PAGE);

  useEffect(() => { setLimit(PAGE); }, [rows]);

  const sorted = useMemo(() => {
    const column = columns.find(c => c.key === sort.key);
    if (!column) return rows;
    const factor = sort.direction === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      const left = column.sort(a);
      const right = column.sort(b);
      if (left === right) return 0;
      if (left === null || left === undefined) return 1;
      if (right === null || right === undefined) return -1;
      return (typeof left === 'number' && typeof right === 'number'
        ? left - right
        : String(left).localeCompare(String(right))) * factor;
    });
  }, [rows, columns, sort]);

  const toggle = useCallback(key => setSort(current => ({
    key,
    direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc',
  })), []);

  return { sorted, visible: sorted.slice(0, limit), sort, toggle, limit, setLimit };
}

function Table({ rows, columns, sort, toggle, empty }) {
  if (!rows.length) return <div className="rt-empty">{empty}</div>;
  return (
    <div className="rt-scroll">
      <table>
        <thead>
          <tr>
            {columns.map(column => (
              <th
                key={column.key}
                className={column.numeric ? 'rt-num' : undefined}
                aria-sort={sort.key === column.key
                  ? (sort.direction === 'asc' ? 'ascending' : 'descending')
                  : 'none'}
              >
                <button type="button" onClick={() => toggle(column.key)}>
                  {column.label}
                  {sort.key === column.key && (sort.direction === 'asc'
                    ? <ArrowUp size={11}/> : <ArrowDown size={11}/>)}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.__key}>
              {columns.map(column => (
                <td key={column.key} className={column.numeric ? 'rt-num' : undefined}>
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Footer({ shown, total, limit, setLimit, onExport, noun }) {
  return (
    <div className="rt-footer">
      <span>Showing {num(shown)} of {num(total)} {noun}</span>
      <div className="rt-footer-actions">
        {shown < total && (
          <button type="button" onClick={() => setLimit(limit + PAGE * 5)}>Show more</button>
        )}
        <button type="button" className="rt-export" onClick={onExport} disabled={!total}>
          <Download size={12}/> Export {num(total)} rows
        </button>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ ontology

function OntologyTable({ model }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const [predicate, setPredicate] = useState('all');
  const [agent, setAgent] = useState('all');

  const label = useCallback(id => model.labels[id] || shortId(id), [model]);
  const predicateLabel = useMemo(
    () => Object.fromEntries(model.predicates.map(p => [p.id, p.label])), [model],
  );
  const agentLabel = useMemo(
    () => Object.fromEntries(model.agents.map(a => [a.id, a.label])), [model],
  );

  const rows = useMemo(() => {
    const term = query.trim().toLowerCase();
    return model.triples
      .filter(t => status === 'all' || t.st === status)
      .filter(t => predicate === 'all' || t.p === predicate)
      .filter(t => agent === 'all' || t.a === agent)
      .filter(t => !term || [
        t.s, t.o, t.id, t.m, label(t.s), t.o ? label(t.o) : literal(t.v),
      ].some(field => field && String(field).toLowerCase().includes(term)))
      .map(t => ({ ...t, __key: t.id }));
  }, [model, query, status, predicate, agent, label]);

  const columns = useMemo(() => [
    {
      key: 'subject', label: 'Subject',
      sort: r => label(r.s),
      csv: r => r.s,
      cell: r => <><strong>{label(r.s)}</strong><small>{r.s}</small></>,
    },
    {
      key: 'predicate', label: 'Predicate',
      sort: r => r.p,
      csv: r => r.p,
      cell: r => <><span className="rt-pred">{predicateLabel[r.p] || r.p}</span><small>{r.p}</small></>,
    },
    {
      key: 'object', label: 'Object or value',
      sort: r => (r.o ? label(r.o) : literal(r.v)),
      csv: r => (r.o ? r.o : literal(r.v)),
      cell: r => (r.o
        ? <><strong>{label(r.o)}</strong><small>{r.o}</small></>
        : <span className="rt-literal">{literal(r.v)}</span>),
    },
    {
      key: 'status', label: 'Status',
      sort: r => r.st,
      csv: r => r.st,
      cell: r => <span className={`rt-chip rt-${r.st}`}>{r.st}</span>,
    },
    {
      key: 'agent', label: 'Asserted by',
      sort: r => agentLabel[r.a] || r.a,
      csv: r => r.a,
      cell: r => <><span>{agentLabel[r.a] || shortId(r.a)}</span><small>{r.m || ''}</small></>,
    },
    {
      key: 'confidence', label: 'Conf.', numeric: true,
      sort: r => r.c,
      csv: r => r.c,
      cell: r => (
        <span className={r.c < model.promoteThreshold ? 'rt-below' : undefined}>
          {r.c.toFixed(2)}
        </span>
      ),
    },
    {
      key: 'reviewed', label: 'Reviewed by',
      sort: r => r.r || '',
      csv: r => r.r || '',
      cell: r => (r.r ? <span className="rt-reviewed">{agentLabel[r.r] || shortId(r.r)}</span> : '—'),
    },
  ], [label, predicateLabel, agentLabel, model.promoteThreshold]);

  const { visible, sorted, sort, toggle, limit, setLimit } = useTable(
    rows, columns, { key: 'subject', direction: 'asc' },
  );

  const counts = model.counts;
  const filtered = query || status !== 'all' || predicate !== 'all' || agent !== 'all';

  return (
    <>
      <div className="rt-summary">
        {['asserted', 'proposed', 'rejected'].map(name => (
          <button
            key={name}
            type="button"
            className={`rt-stat rt-stat-${name} ${status === name ? 'active' : ''}`}
            onClick={() => setStatus(status === name ? 'all' : name)}
          >
            <strong>{num(counts[name] || 0)}</strong>
            <span>{name}</span>
          </button>
        ))}
        <div className="rt-stat rt-stat-note">
          <strong>{num(counts.total)}</strong>
          <span>facts in the graph</span>
        </div>
      </div>

      <div className="rt-controls">
        <div className="rt-search">
          <Search size={13}/>
          <input
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Search subject, object, value or assertion id"
            aria-label="Search the ontology table"
          />
          {query && (
            <button type="button" onClick={() => setQuery('')} aria-label="Clear search">
              <X size={12}/>
            </button>
          )}
        </div>
        <label className="rt-select">
          <span>Predicate</span>
          <select value={predicate} onChange={event => setPredicate(event.target.value)}>
            <option value="all">All predicates</option>
            {model.predicates.map(p => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </label>
        <label className="rt-select">
          <span>Status</span>
          <select value={status} onChange={event => setStatus(event.target.value)}>
            <option value="all">All statuses</option>
            <option value="asserted">Asserted</option>
            <option value="proposed">Proposed</option>
            <option value="rejected">Rejected</option>
          </select>
        </label>
        <label className="rt-select">
          <span>Agent</span>
          <select value={agent} onChange={event => setAgent(event.target.value)}>
            <option value="all">All agents</option>
            {model.agents.map(a => (
              <option key={a.id} value={a.id}>{a.label}</option>
            ))}
          </select>
        </label>
        {filtered && (
          <button
            type="button"
            className="rt-clear"
            onClick={() => { setQuery(''); setStatus('all'); setPredicate('all'); setAgent('all'); }}
          >
            <Filter size={12}/> Clear filters
          </button>
        )}
      </div>

      {predicate !== 'all' && (
        <p className="rt-definition">
          {model.predicates.find(p => p.id === predicate)?.definition}
        </p>
      )}

      <Table
        rows={visible}
        columns={columns}
        sort={sort}
        toggle={toggle}
        empty="No assertion matches these filters."
      />
      <Footer
        shown={visible.length}
        total={sorted.length}
        limit={limit}
        setLimit={setLimit}
        noun="facts"
        onExport={() => download('uzgeodata-ontology-facts.csv', sorted, columns)}
      />
    </>
  );
}

// ------------------------------------------------------------------ features

function FeatureTable({ graph }) {
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [scope, setScope] = useState('basin');

  const index = useMemo(() => {
    const basins = new Map(graph.basins.map(b => [b.id, b]));
    const reaches = new Map();
    const lakes = new Map();
    const upstream = new Map();
    const push = (map, key, value) => {
      if (!key) return;
      const bucket = map.get(key);
      if (bucket) bucket.push(value); else map.set(key, [value]);
    };
    graph.rivers.forEach(river => push(reaches, river.basinId, river));
    graph.lakes.forEach(lake => push(lakes, lake.basinId, lake));
    graph.basins.forEach(basin => push(upstream, basin.nextDown, basin.id));
    return { basins, reaches, lakes, upstream };
  }, [graph]);

  const ranked = useMemo(() => {
    const term = query.trim().toLowerCase();
    return graph.basins
      .filter(basin => !term
        || String(basin.id).includes(term)
        || String(basin.pfafId).includes(term))
      .sort((a, b) => (b.uzbekistanKm2 ?? 0) - (a.uzbekistanKm2 ?? 0))
      .slice(0, 260);
  }, [graph, query]);

  const basin = selectedId ? index.basins.get(selectedId) : null;

  // Walking the inverted NEXT_DOWN index is the only way to go upstream: the
  // measured edge points downstream, and nothing stores its inverse.
  const inScope = useMemo(() => {
    if (!basin) return [];
    if (scope === 'basin') return [basin.id];
    const seen = new Set([basin.id]);
    const stack = [basin.id];
    while (stack.length) {
      (index.upstream.get(stack.pop()) || []).forEach(child => {
        if (!seen.has(child)) { seen.add(child); stack.push(child); }
      });
    }
    return [...seen];
  }, [basin, scope, index]);

  const reaches = useMemo(
    () => inScope.flatMap(id => index.reaches.get(id) || []).map(r => ({ ...r, __key: r.id })),
    [inScope, index],
  );
  const lakes = useMemo(
    () => inScope.flatMap(id => index.lakes.get(id) || []).map(l => ({ ...l, __key: l.id })),
    [inScope, index],
  );

  const reachColumns = useMemo(() => [
    { key: 'id', label: 'Reach', sort: r => r.id, csv: r => r.id,
      cell: r => <span className="rt-id">{r.id}</span> },
    { key: 'basin', label: 'Basin', sort: r => r.basinId, csv: r => r.basinId,
      cell: r => <span className="rt-id">{r.basinId}</span> },
    { key: 'order', label: 'Strahler', numeric: true, sort: r => r.strahlerOrder,
      csv: r => r.strahlerOrder, cell: r => num(r.strahlerOrder) },
    { key: 'length', label: 'Length km', numeric: true, sort: r => r.lengthKm,
      csv: r => r.lengthKm, cell: r => num(r.lengthKm, 2) },
    { key: 'catchment', label: 'Catchment km²', numeric: true, sort: r => r.catchmentKm2,
      csv: r => r.catchmentKm2, cell: r => num(r.catchmentKm2, 2) },
    { key: 'upstream', label: 'Upstream km²', numeric: true, sort: r => r.upstreamKm2,
      csv: r => r.upstreamKm2, cell: r => num(r.upstreamKm2, 1) },
    { key: 'discharge', label: 'Discharge m³/s', numeric: true, sort: r => r.dischargeCms,
      csv: r => r.dischargeCms, cell: r => num(r.dischargeCms, 3) },
    { key: 'nextDown', label: 'Flows into', sort: r => r.nextDown, csv: r => r.nextDown || '',
      cell: r => (r.nextDown ? <span className="rt-id">{r.nextDown}</span> : <em>outlet</em>) },
  ], []);

  const lakeColumns = useMemo(() => [
    { key: 'id', label: 'Lake', sort: r => r.id, csv: r => r.id,
      cell: r => <span className="rt-id">{r.id}</span> },
    { key: 'name', label: 'Name', sort: r => r.name || '', csv: r => r.name || '',
      cell: r => r.name || <em>unnamed</em> },
    { key: 'basin', label: 'Basin', sort: r => r.basinId, csv: r => r.basinId,
      cell: r => <span className="rt-id">{r.basinId}</span> },
    { key: 'area', label: 'Area km²', numeric: true, sort: r => r.areaKm2,
      csv: r => r.areaKm2, cell: r => num(r.areaKm2, 2) },
    { key: 'volume', label: 'Volume MCM', numeric: true, sort: r => r.volumeMcm,
      csv: r => r.volumeMcm, cell: r => num(r.volumeMcm, 1) },
    { key: 'depth', label: 'Mean depth m', numeric: true, sort: r => r.depthM,
      csv: r => r.depthM, cell: r => num(r.depthM, 2) },
    { key: 'elevation', label: 'Elevation m', numeric: true, sort: r => r.elevationM,
      csv: r => r.elevationM, cell: r => num(r.elevationM) },
    { key: 'discharge', label: 'Discharge m³/s', numeric: true, sort: r => r.dischargeCms,
      csv: r => r.dischargeCms, cell: r => num(r.dischargeCms, 3) },
  ], []);

  const reachTable = useTable(reaches, reachColumns, { key: 'upstream', direction: 'desc' });
  const lakeTable = useTable(lakes, lakeColumns, { key: 'area', direction: 'desc' });

  return (
    <div className="rt-feature-layout">
      <aside className="rt-basins">
        <div className="rt-panel-label">
          <Database size={12}/><span>BASIN REFERENCE</span>
          <small>{num(graph.basins.length)}</small>
        </div>
        <div className="rt-search rt-search-inline">
          <Search size={13}/>
          <input
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Basin or Pfafstetter id"
            aria-label="Search basins"
          />
        </div>
        <div className="rt-basin-list">
          {ranked.map(item => (
            <button
              key={item.id}
              type="button"
              className={item.id === selectedId ? 'selected' : undefined}
              onClick={() => setSelectedId(item.id)}
            >
              <span className="rt-id">{item.id}</span>
              <small>
                {num(item.uzbekistanKm2, 1)} km² · {num(item.uzbekistanPercent, 0)}% in UZ
                {(index.reaches.get(item.id) || []).length
                  ? ` · ${(index.reaches.get(item.id) || []).length} reaches`
                  : ' · no reach'}
              </small>
            </button>
          ))}
          {!ranked.length && <div className="rt-empty">No basin matches.</div>}
        </div>
      </aside>

      <div className="rt-feature-main">
        {!basin ? (
          <div className="rt-empty rt-empty-tall">
            <Network size={26}/>
            <p>Pick a basin to list every river reach and water body that resolves to it.</p>
          </div>
        ) : (
          <>
            <div className="rt-basin-head">
              <div>
                <span className="rt-kicker">BASIN</span>
                <h2>{basin.id}</h2>
                <p>Pfafstetter {basin.pfafId}</p>
              </div>
              <div className="rt-metrics">
                <div><span>Sub-basin area</span><strong>{num(basin.areaKm2, 1)} km²</strong></div>
                <div><span>In Uzbekistan</span><strong>{num(basin.uzbekistanKm2, 1)} km²</strong></div>
                <div><span>Share in country</span><strong>{num(basin.uzbekistanPercent, 1)}%</strong></div>
                <div><span>Upstream area</span><strong>{num(basin.upstreamKm2, 1)} km²</strong></div>
                <div>
                  <span>Drains into</span>
                  <strong>
                    {basin.nextDown
                      ? (index.basins.has(basin.nextDown)
                        ? basin.nextDown
                        : `${basin.nextDown} (outside)`)
                      : 'sink'}
                  </strong>
                </div>
                <div><span>Endorheic</span><strong>{basin.endorheic ? 'Yes' : 'No'}</strong></div>
              </div>
            </div>

            <div className="rt-scope">
              <span>Scope</span>
              {[['basin', 'This basin'], ['upstream', 'This basin + everything upstream']].map(
                ([value, text]) => (
                  <button
                    key={value}
                    type="button"
                    className={scope === value ? 'active' : undefined}
                    onClick={() => setScope(value)}
                  >
                    {text}
                  </button>
                ),
              )}
              <small>
                {num(inScope.length)} basin{inScope.length === 1 ? '' : 's'} in scope
                {scope === 'upstream' && !index.basins.has(basin.nextDown) && basin.nextDown
                  ? ' · downstream leaves the selection'
                  : ''}
              </small>
            </div>

            <section className="rt-section">
              <div className="rt-panel-label">
                <Waves size={12}/><span>RIVER REACHES</span>
                <small>uz:drainsToBasin · {num(reaches.length)}</small>
              </div>
              <Table
                rows={reachTable.visible}
                columns={reachColumns}
                sort={reachTable.sort}
                toggle={reachTable.toggle}
                empty="No river reach resolves to this basin."
              />
              <Footer
                shown={reachTable.visible.length}
                total={reachTable.sorted.length}
                limit={reachTable.limit}
                setLimit={reachTable.setLimit}
                noun="reaches"
                onExport={() => download(`basin-${basin.id}-reaches.csv`, reachTable.sorted, reachColumns)}
              />
            </section>

            <section className="rt-section">
              <div className="rt-panel-label">
                <Database size={12}/><span>WATER BODIES</span>
                <small>uz:withinBasin · {num(lakes.length)}</small>
              </div>
              <Table
                rows={lakeTable.visible}
                columns={lakeColumns}
                sort={lakeTable.sort}
                toggle={lakeTable.toggle}
                empty="No water body sits in this basin."
              />
              <Footer
                shown={lakeTable.visible.length}
                total={lakeTable.sorted.length}
                limit={lakeTable.limit}
                setLimit={lakeTable.setLimit}
                noun="water bodies"
                onExport={() => download(`basin-${basin.id}-lakes.csv`, lakeTable.sorted, lakeColumns)}
              />
            </section>
          </>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ shell

const VIEWS = {
  ontology: { label: 'Ontology facts', icon: Table2, url: TRIPLES_URL },
  features: { label: 'Basin features', icon: Waves, url: FEATURES_URL },
};

export default function RelationshipTables() {
  const [view, setView] = useState('ontology');
  const [data, setData] = useState({});
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const requested = useRef(new Set());

  useEffect(() => {
    if (requested.current.has(view)) { setLoading(false); return; }
    requested.current.add(view);
    setLoading(true);
    fetch(VIEWS[view].url)
      .then(response => (response.ok
        ? response.json()
        : Promise.reject(new Error(`${response.status} ${response.statusText}`))))
      .then(payload => setData(current => ({ ...current, [view]: payload })))
      .catch(cause => setError(cause.message))
      .finally(() => setLoading(false));
  }, [view]);

  const payload = data[view];

  return (
    <div className="rt-app">
      <header className="rt-header">
        <a href="/" className="rt-logo" aria-label="UzGeoData home">
          <svg viewBox="0 0 38 38" aria-hidden="true">
            <path d="M5 7h8v15c0 5 2 8 6 8s6-3 6-8V7h8v16c0 9-5 14-14 14S5 32 5 23V7Z"/>
            <path className="rt-logo-bar" d="M13 2h21v5H13z"/>
          </svg>
          <span>UZ<span>GEO</span>DATA</span>
        </a>
        <div className="rt-header-title">
          <span>RELATIONSHIP BROWSER</span>
          <strong>Every stored link, in a table</strong>
        </div>
        <nav>
          <a href="/">Portal</a>
          <a href="/hydrography.html">Map explorer</a>
          <a href="/relationships.html" className="active">Tables</a>
          <a href="/catalogue.html">Catalogue</a>
          <a href="/review.html">Review</a>
        </nav>
      </header>

      <main className="rt-main">
        <div className="rt-tabs" role="tablist">
          {Object.entries(VIEWS).map(([key, entry]) => {
            const Icon = entry.icon;
            return (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={view === key}
                className={view === key ? 'active' : undefined}
                onClick={() => setView(key)}
              >
                <Icon size={13}/>{entry.label}
              </button>
            );
          })}
        </div>

        {error && (
          <div className="rt-error">
            <h2>Could not load the table</h2>
            <p>{error}</p>
            <p>
              Rebuild with <code>npm run ontology:build</code> for the ontology table, or{' '}
              <code>npm run hydrography:build</code> for the basin features, then reload.
            </p>
          </div>
        )}

        {!error && loading && !payload && (
          <div className="rt-loading"><LoaderCircle size={15}/> Loading {VIEWS[view].label.toLowerCase()}</div>
        )}

        {!error && payload && view === 'ontology' && <OntologyTable model={payload}/>}
        {!error && payload && view === 'features' && <FeatureTable graph={payload}/>}
      </main>
    </div>
  );
}
