import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, ArrowUpRight, ChevronDown, ChevronRight, CircleCheck, Database,
  FolderTree, HardDrive, Layers, LoaderCircle, MapPin, Search, Sparkles, Tag,
} from 'lucide-react';

// The data inventory: every dataset the ontology knows about, what it measures,
// where it came from, and whether anything here can actually open it.
//
// The availability column is the point of the page. The graph records where a
// file is meant to live, which is not the same as where one is, and most of the
// atlas derivatives sit in an untracked workspace or on a drive that was profiled
// once and then unplugged. Sorting by that difference is what turns a list of
// datasets into a picture of scope.

const CATALOGUE_URL = '/data/data-catalogue.json';
const GROUPS_URL = '/data/data-groups.json';

// The status a group carries is measured against this working copy, not declared,
// so the colour says something real: green means the bytes are on the disk you are
// reading this from.
const GROUP_STATUS = {
  HELD: { tone: 'ok', label: 'On this PC' },
  PARTIAL: { tone: 'warn', label: 'Partly here' },
  WORKSPACE: { tone: 'warn', label: 'In workspace' },
  OFFLINE: { tone: 'cold', label: 'Offline drive' },
  ABSENT: { tone: 'bad', label: 'Not here' },
};

const AVAILABILITY = {
  published: {
    label: 'Published', icon: CircleCheck,
    blurb: 'Served by the portal right now — the file is in PUBLISHED/ and the URL resolves.',
  },
  workspace: {
    label: 'In workspace', icon: FolderTree,
    blurb: 'Declared with a URL, but the file is not in this checkout. It is built into WORKSPACE/, '
      + 'which is deliberately untracked, so these URLs return the app shell rather than data.',
  },
  offline: {
    label: 'Offline drive', icon: HardDrive,
    blurb: 'Only ever seen on an external drive. The profile records the path, size and structure; '
      + 'the bytes are somewhere else.',
  },
};

const bytes = value => {
  if (!value) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
  return `${size < 10 && unit > 0 ? size.toFixed(1) : Math.round(size)} ${units[unit]}`;
};

const num = value => (value === null || value === undefined ? '—' : Number(value).toLocaleString('en-US'));

function Row({ row, expanded, onToggle }) {
  const state = AVAILABILITY[row.availability] || AVAILABILITY.workspace;
  const StateIcon = state.icon;
  return <>
    <tr className={expanded ? 'cat-row cat-row-open' : 'cat-row'} onClick={onToggle}>
      <td className="cat-cell-name">
        {expanded ? <ChevronDown size={13}/> : <ChevronRight size={13}/>}
        <div>
          <strong>{row.label}</strong>
          {row.labels?.ru && row.labels.ru !== row.label && <em>{row.labels.ru}</em>}
        </div>
      </td>
      <td>{row.theme ? <span className="cat-tag">{row.theme.label}</span> : <span className="cat-none">unclassified</span>}</td>
      <td className="cat-cell-observes">
        {row.observes.length
          ? row.observes.slice(0, 3).map(o => o.label).join(', ') + (row.observes.length > 3 ? ` +${row.observes.length - 3}` : '')
          : <span className="cat-none">—</span>}
      </td>
      <td className="cat-mono">{row.temporal ? `${row.temporal.start}–${row.temporal.end}` : <span className="cat-none">—</span>}</td>
      <td className="cat-mono">{bytes(row.bytes)}</td>
      <td><span className={`cat-state cat-state-${row.availability}`}><StateIcon size={11}/>{state.label}</span></td>
    </tr>
    {expanded && <tr className="cat-detail-row"><td colSpan={6}>
      <div className="cat-detail">
        {row.description && <p className="cat-description">{row.description}</p>}
        <div className="cat-detail-grid">
          <div>
            <span>Measures</span>
            <div className="cat-chips">
              {row.observes.length ? row.observes.map(o => <i key={o.id}>{o.label}</i>) : <span className="cat-none">nothing recorded</span>}
            </div>
          </div>
          <div>
            <span>Covers</span>
            <div className="cat-chips">
              {row.places.length ? row.places.map(p => <i key={p.id}>{p.label}</i>) : <span className="cat-none">no place recorded</span>}
            </div>
          </div>
          <div>
            <span>Supports</span>
            <div className="cat-chips">
              {row.useCases.length ? row.useCases.map(u => <i key={u.id}>{u.label}</i>) : <span className="cat-none">no use case recorded</span>}
            </div>
          </div>
          <div>
            <span>Licence</span>
            <div className="cat-chips">
              {row.license ? <i>{row.license}</i> : <span className="cat-none">not cleared</span>}
            </div>
          </div>
        </div>

        {row.attribution && <p className="cat-attribution">Attributed to {row.attribution}</p>}

        {!!row.quality.length && <div className="cat-flags">
          <AlertTriangle size={12}/>
          {row.quality.map(flag => <span key={flag}>{flag.replace(/-/g, ' ')}</span>)}
        </div>}

        <div className="cat-dist-title">Distributions &middot; {row.distributions.length}</div>
        <table className="cat-dist">
          <thead><tr><th>File</th><th>Role</th><th>Format</th><th>Size</th><th>Where it is</th></tr></thead>
          <tbody>
            {row.distributions.map(dist => <tr key={dist.id}>
              <td>{dist.label}</td>
              <td className="cat-mono">{dist.role}</td>
              <td className="cat-mono">{dist.format || '—'}</td>
              <td className="cat-mono">{bytes(dist.bytes)}</td>
              <td className="cat-where">
                {dist.availability === 'published' && <a href={dist.url} target="_blank" rel="noreferrer">{dist.url} <ArrowUpRight size={10}/></a>}
                {dist.availability === 'workspace' && <code title="declared, but absent from this checkout">{dist.url || 'WORKSPACE/'}</code>}
                {dist.availability === 'offline' && <code title={dist.inventory || 'external drive'}>{dist.externalPath || dist.inventory || 'external drive'}</code>}
              </td>
            </tr>)}
          </tbody>
        </table>
      </div>
    </td></tr>}
  </>;
}

export default function DataCatalogue() {
  const [data, setData] = useState(null);
  const [groups, setGroups] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [theme, setTheme] = useState('all');
  const [availability, setAvailability] = useState('all');
  const [open, setOpen] = useState(null);

  useEffect(() => {
    fetch(CATALOGUE_URL)
      .then(response => (response.ok ? response.json() : Promise.reject(new Error(`${response.status} ${response.statusText}`))))
      .then(setData)
      .catch(cause => setError(cause.message));
    fetch(GROUPS_URL)
      .then(response => (response.ok ? response.json() : Promise.reject(new Error())))
      .then(setGroups)
      .catch(() => setGroups(null));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    const term = query.trim().toLowerCase();
    return data.datasets
      .filter(row => theme === 'all' || row.theme?.label === theme)
      .filter(row => availability === 'all' || row.availability === availability)
      .filter(row => !term
        || (row.label || '').toLowerCase().includes(term)
        || (row.labels?.ru || '').toLowerCase().includes(term)
        || (row.description || '').toLowerCase().includes(term)
        || row.observes.some(o => o.label.toLowerCase().includes(term)));
  }, [data, query, theme, availability]);

  if (error) return <div className="cat-fatal">
    <h1>Catalogue unavailable</h1>
    <p>{error}</p>
    <p>Rebuild it with <code>npm run catalogue:build</code>, then reload.</p>
    <a href="/">Return to the portal</a>
  </div>;

  if (!data) return <div className="cat-loading"><LoaderCircle size={16}/> Loading the data catalogue</div>;

  const { summary, gaps, inventories } = data;
  const offlineGb = (summary.offlineBytes / 1e9).toFixed(1);
  const transboundary = gaps.placesWithoutData.map(p => p.label);

  return <div className="cat-app">
    <header className="cat-header">
      <a href="/" className="cat-logo" aria-label="UzGeoData home">
        <svg viewBox="0 0 38 38" aria-hidden="true"><path d="M5 7h8v15c0 5 2 8 6 8s6-3 6-8V7h8v16c0 9-5 14-14 14S5 32 5 23V7Z"/><path className="cat-logo-bar" d="M13 2h21v5H13z"/></svg>
        <span>UZ<span>GEO</span>DATA</span>
      </a>
      <div className="cat-header-title">
        <span>STORED ONTOLOGY</span>
        <strong>Data catalogue</strong>
      </div>
      <nav>
        <a href="/">Portal</a>
        <a href="/hydrography.html">Explorer</a>
        <a href="/relationships.html">Tables</a>
        <a href="/review.html">Review</a>
        <a href="#groups" className="active">Groups</a>
        <a href="#inventory">Catalogue</a>
        <a href="#scope">Scope</a>
      </nav>
    </header>

    <main className="cat-main">
      <section className="cat-intro">
        <div>
          <span className="cat-kicker">WHAT THE PORTAL KNOWS ABOUT</span>
          <h1>Every dataset, <span>and where it actually is</span></h1>
          <p>
            The stored graph describes {num(summary.datasets)} datasets across {num(summary.distributions)} files.
            Most of them are not in this checkout. The atlas derivatives are built into an untracked
            workspace, and {num(summary.availability.offline || 0)} datasets were profiled on external
            drives and never copied in — {offlineGb} GB of them. Nothing is hidden for being missing:
            a dataset that exists only as a path on a desktop is still part of the scope, and the
            catalogue says so rather than pretending otherwise.
          </p>
        </div>
        <div className="cat-stat-grid">
          <div><Database size={18}/><strong>{num(summary.datasets)}</strong><span>Datasets</span></div>
          <div><Layers size={18}/><strong>{num(summary.distributions)}</strong><span>Files described</span></div>
          <div><MapPin size={18}/><strong>{num(summary.stations)}</strong><span>Monitoring stations</span></div>
          <div><HardDrive size={18}/><strong>{offlineGb} GB</strong><span>Offline, profiled only</span></div>
        </div>
      </section>

      <section className="cat-states">
        {Object.entries(AVAILABILITY).map(([key, entry]) => {
          const Icon = entry.icon;
          return <div key={key} className={`cat-state-card cat-state-card-${key}`}>
            <div><Icon size={14}/><strong>{entry.label}</strong><em>{num(summary.availability[key] || 0)}</em></div>
            <p>{entry.blurb}</p>
          </div>;
        })}
      </section>

      {groups && <section className="cat-groups" id="groups">
        <div className="cat-section-head">
          <span className="cat-kicker">DATA GROUPS</span>
          <h2>What this project has, and where</h2>
          <p>
            Every kind of data the project references, with a short code to refer to it by. The
            status is checked against this working copy rather than taken from a record, because
            most of what the graph describes lives somewhere else — an untracked workspace, a
            Windows drive that was profiled once, or a service that has never been fetched here.
          </p>
        </div>

        <div className="cat-group-key">
          {Object.entries(GROUP_STATUS).map(([key, entry]) => <span key={key} className={`cat-badge cat-badge-${entry.tone}`}>
            {entry.label}
            <em>{groups.summary[key] || 0}</em>
          </span>)}
        </div>

        <div className="cat-table-shell">
          <table className="cat-table cat-group-table">
            <thead>
              <tr>
                <th>Code</th><th>Group</th><th>What it is</th><th>Scale</th><th>Size here</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {groups.groups.map(group => {
                const state = GROUP_STATUS[group.status] || GROUP_STATUS.ABSENT;
                return <tr key={group.code} className="cat-row">
                  <td><code className="cat-code">{group.code}</code></td>
                  <td><strong>{group.title}</strong><em className="cat-group-source">{group.source}</em></td>
                  <td className="cat-group-what">
                    {group.what}
                    {group.note && <span className="cat-group-note">{group.note}</span>}
                  </td>
                  <td className="cat-mono">{group.scale || '—'}</td>
                  <td className="cat-mono">{group.bytes ? bytes(group.bytes) : '—'}</td>
                  <td><span className={`cat-badge cat-badge-${state.tone}`}>{state.label}</span></td>
                </tr>;
              })}
            </tbody>
          </table>
        </div>
        <div className="cat-table-foot">
          Checked {new Date(groups.generatedAt).toLocaleString('en-GB')}. Rebuild with
          {' '}<code>npm run data:groups</code>.
        </div>
      </section>}

      <section className="cat-inventory" id="inventory">
        <div className="cat-controls">
          <div className="cat-search">
            <Search size={13}/>
            <input
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder="Search by name, Russian title, description or what it measures"
              aria-label="Search the catalogue"
            />
          </div>
          <select value={theme} onChange={event => setTheme(event.target.value)} aria-label="Filter by theme">
            <option value="all">All themes ({num(summary.datasets)})</option>
            {data.themes.filter(t => t.datasets).map(t =>
              <option key={t.id} value={t.label}>{t.label} ({t.datasets})</option>)}
          </select>
          <select value={availability} onChange={event => setAvailability(event.target.value)} aria-label="Filter by availability">
            <option value="all">Any availability</option>
            {Object.entries(AVAILABILITY).map(([key, entry]) =>
              <option key={key} value={key}>{entry.label} ({num(summary.availability[key] || 0)})</option>)}
          </select>
        </div>

        <div className="cat-table-shell">
          <table className="cat-table">
            <thead>
              <tr>
                <th>Dataset</th><th>Theme</th><th>Measures</th><th>Period</th><th>Size</th><th>Availability</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => <Row
                key={row.id}
                row={row}
                expanded={open === row.id}
                onToggle={() => setOpen(open === row.id ? null : row.id)}
              />)}
              {!rows.length && <tr><td colSpan={6} className="cat-empty">Nothing matches this filter.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="cat-table-foot">
          Showing {num(rows.length)} of {num(summary.datasets)} datasets. Select a row for its
          description, provenance and the files behind it.
        </div>
      </section>

      <section className="cat-scope" id="scope">
        <div className="cat-section-head">
          <span className="cat-kicker">SCOPE</span>
          <h2>What is covered, and what is not</h2>
        </div>

        <div className="cat-scope-grid">
          <div className="cat-panel">
            <div className="cat-panel-label"><Tag size={12}/><span>THEMES</span></div>
            {data.themes.map(theme => <div key={theme.id} className="cat-bar">
              <div><strong>{theme.label}</strong><em>{theme.datasets}</em></div>
              <i style={{ width: `${(theme.datasets / summary.datasets) * 100}%` }}/>
              <p>{theme.definition}</p>
            </div>)}
          </div>

          <div className="cat-panel">
            <div className="cat-panel-label"><HardDrive size={12}/><span>PROFILED DRIVES</span></div>
            {inventories.map(inventory => <div key={inventory.id} className="cat-drive">
              <strong>{inventory.id}</strong>
              <code>{inventory.source}</code>
              <div className="cat-drive-figures">
                <span>{num(inventory.files)} files</span>
                <span>{(inventory.bytes / 1e9).toFixed(2)} GB</span>
                <span>profiled {new Date(inventory.profiledAt).toLocaleDateString('en-GB')}</span>
              </div>
              <div className="cat-chips">
                {Object.entries(inventory.byKind).map(([kind, count]) => <i key={kind}>{kind} {count}</i>)}
              </div>
            </div>)}
            <p className="cat-note">
              These were read once and catalogued. The paths are Windows drives that are not attached
              here, so the profile — layer names, geometry types, row counts, sizes — is all that
              survives of them in this repository.
            </p>
          </div>

          <div className="cat-panel">
            <div className="cat-panel-label"><Layers size={12}/><span>LAYERS THE PORTAL RENDERS</span></div>
            <table className="cat-mini">
              <tbody>
                {data.layers.map(layer => <tr key={layer.id}>
                  <td>{layer.label}</td>
                  <td className="cat-mono">{layer.geometryType}</td>
                  <td className="cat-mono">{num(layer.featureCount)}</td>
                  <td>{layer.available
                    ? <span className="cat-ok"><CircleCheck size={11}/> live</span>
                    : <span className="cat-bad"><AlertTriangle size={11}/> missing</span>}</td>
                </tr>)}
              </tbody>
            </table>
            <p className="cat-note">
              Eight layers plus the three HydroSHEDS references are the whole of what a visitor can
              actually load today, against {num(summary.datasets)} datasets in the graph.
            </p>
          </div>
        </div>
      </section>

      <section className="cat-gaps" id="gaps">
        <div className="cat-section-head">
          <span className="cat-kicker">GAPS</span>
          <h2>Where the ontology is thin</h2>
          <p>
            Each of these is subtracted from the graph rather than judged by eye: a vocabulary concept
            nothing points at, or a field the datasets leave empty.
          </p>
        </div>

        <div className="cat-gap-grid">
          <div className="cat-gap cat-gap-hot">
            <strong>{gaps.placesWithoutData.length}</strong>
            <span>places defined, no data</span>
            <p>{transboundary.join(', ')} — every one of them upstream or transboundary.</p>
          </div>
          <div className="cat-gap">
            <strong>{gaps.datasetsWithoutLicense.length}</strong>
            <span>datasets with no licence</span>
            <p>Of {num(summary.datasets)}. Until a licence is recorded, none of these can be republished.</p>
          </div>
          <div className="cat-gap">
            <strong>{gaps.datasetsWithoutTemporalCoverage.length}</strong>
            <span>with no period recorded</span>
            <p>Which rules them out of any change-over-time question until dated.</p>
          </div>
          <div className="cat-gap">
            <strong>{summary.availability.workspace || 0}</strong>
            <span>declared but absent here</span>
            <p>Their URLs return the app shell with a 200, so a client sees HTML where it expects JSON.</p>
          </div>
          <div className="cat-gap">
            <strong>{gaps.propertiesWithoutData.length}</strong>
            <span>properties nothing measures</span>
            <p>{gaps.propertiesWithoutData.map(p => p.label).join(', ')}.</p>
          </div>
          <div className="cat-gap">
            <strong>{Object.values(gaps.qualityFlags).reduce((a, b) => a + b, 0)}</strong>
            <span>quality flags raised</span>
            <p>{Object.entries(gaps.qualityFlags).slice(0, 3).map(([flag, count]) => `${flag.replace(/-/g, ' ')} (${count})`).join(', ')}.</p>
          </div>
        </div>
      </section>

      <section className="cat-recommend" id="recommendations">
        <div className="cat-section-head">
          <span className="cat-kicker">WHAT WOULD STRENGTHEN IT</span>
          <h2>Suggestions, in the order they pay off</h2>
        </div>

        <ol className="cat-recs">
          <li>
            <div><Sparkles size={14}/><h3>Upstream basins for the four neighbours and Afghanistan</h3></div>
            <p>
              The strongest signal on this page is that all {gaps.placesWithoutData.length} empty places are
              transboundary. It is the same hole that stops the watershed tracer: an Amu Darya outlet
              reports 622,507 km² upstream, and the clipped network can only walk 11% of it, because the
              headwaters are in Tajikistan, Kyrgyzstan and Afghanistan. HydroSHEDS is global and already
              licensed here — re-clipping HydroBASINS, HydroRIVERS and BasinATLAS to the Aral Sea
              basin rather than the national border would close the ontology gap and make the tracer
              honest in one step, with no new data licence to negotiate.
            </p>
            <em>New layers: basins, rivers and BasinATLAS attributes on the Aral Sea basin extent.</em>
          </li>
          <li>
            <div><Tag size={14}/><h3>Record a licence for the {gaps.datasetsWithoutLicense.length} datasets that have none</h3></div>
            <p>
              This is the cheapest item and it gates everything else: it is metadata work, not
              acquisition. {num(gaps.qualityFlags['licence-not-cleared-for-publication'] || 0)} datasets are
              already flagged <code>licence-not-cleared-for-publication</code>{' '}
              and {num(gaps.qualityFlags['licence-terms-to-confirm-before-redistribution'] || 0)} more{' '}
              <code>licence-terms-to-confirm</code>, so the portal cannot legally serve
              them even once the files are in place. Clearing licences turns held data into publishable data.
            </p>
            <em>No new data — a field on 135 existing records.</em>
          </li>
          <li>
            <div><FolderTree size={14}/><h3>Publish, or stop advertising, the {summary.availability.workspace || 0} workspace datasets</h3></div>
            <p>
              These carry URLs that return the app shell with a 200 rather than a 404, which is the
              worst of both: a client cannot tell the data is missing, and neither can a reader.
              Either build them into <code>PUBLISHED/</code> or mark them plainly as internal. A 404
              for an absent file would at least be truthful.
            </p>
            <em>Build step, plus a fallback that does not answer 200 for data paths.</em>
          </li>
          <li>
            <div><MapPin size={14}/><h3>Attach the 190 monitoring stations to what they measure</h3></div>
            <p>
              The graph holds {num(summary.stations)} gauges with coordinates and a network, but they
              sit apart from the basins they fall inside. A point-in-polygon join to the level-12
              basins would let any traced catchment list the gauges inside it — which is the question
              a hydrologist asks first, and the one the explorer cannot answer today.
            </p>
            <em>New relationship table: station → basin, and station → observed property.</em>
          </li>
          <li>
            <div><Database size={14}/><h3>Date the {gaps.datasetsWithoutTemporalCoverage.length} undated datasets</h3></div>
            <p>
              Over half the catalogue has no period recorded, which quietly excludes it from every
              change-detection question the use-case vocabulary already defines. Many are atlas
              packages whose source titles carry the years; the rest need a look at the source.
            </p>
            <em>No new data — a temporal field, partly recoverable from existing titles.</em>
          </li>
          <li>
            <div><HardDrive size={14}/><h3>Bring the {offlineGb} GB of profiled drives in, or drop them</h3></div>
            <p>
              Two drives were catalogued and never copied: {inventories.map(i => i.id).join(' and ')}.
              The profiles are good enough to plan against — layer names, geometry types, row counts —
              but not to compute with. Decide per dataset whether it belongs in the portal, and retire
              the rest so the catalogue stops promising what nobody can open.
            </p>
            <em>Ingest decision on {num(inventories.reduce((total, i) => total + i.files, 0))} profiled files.</em>
          </li>
        </ol>
      </section>
    </main>

    <footer className="cat-footer">
      <span>Built from the stored ontology &middot; {num(summary.datasets)} datasets &middot; generated {new Date(data.generatedAt).toLocaleString('en-GB')}</span>
      <a href="/">Back to the portal <ArrowUpRight size={13}/></a>
    </footer>
  </div>;
}
