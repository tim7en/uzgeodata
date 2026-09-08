import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, BookOpen, Database, ExternalLink, Scale, Search, Layers } from 'lucide-react';

const CATALOGUE_URL = '/data/hydroclimate/reference-attribute-catalogue.json';
const GROUP_LABELS = {
  basin_specific: 'sub-basin',
  basin_accumulation: 'upstream',
};

const json = url => fetch(url).then(response => response.ok
  ? response.json()
  : Promise.reject(new Error(`${response.status} while loading ${url}`)));

const count = value => Number(value || 0).toLocaleString('en-US');

function Variable({ variable }) {
  const [open, setOpen] = useState(false);
  return <article className={`meta-card ${open ? 'open' : ''}`}>
    <header>
      <div>
        <span className="meta-cat">{variable.category}</span>
        <h3>{variable.label}</h3>
        <p>{variable.description}</p>
      </div>
      <code>{variable.code}</code>
    </header>

    <dl className="meta-facts">
      <div><dt>Source product</dt><dd>{variable.source || '—'}</dd></div>
      <div><dt>Native resolution</dt><dd>{variable.nativeFormat || '—'}</dd></div>
      <div><dt>Units</dt><dd>{variable.units || '—'}</dd></div>
      <div><dt>Catalogue</dt><dd>{variable.catalogueId || '—'}</dd></div>
    </dl>

    <p className="meta-cite"><BookOpen size={11}/> {variable.citation || 'Citation not recorded'}</p>
    <p className="meta-licence"><Scale size={11}/> {variable.licence || 'Licence not recorded'}</p>

    <button type="button" onClick={() => setOpen(current => !current)}>
      {open ? 'Hide' : 'Show'} {variable.columnCount} column{variable.columnCount === 1 ? '' : 's'} on the reference basins
    </button>
    {open && <table className="meta-columns">
      <thead><tr><th>Column</th><th>Measured over</th><th>Dimension</th><th>Kind</th></tr></thead>
      <tbody>{variable.columns.map(column => <tr key={column.column}>
        <td><code>{column.column}</code></td>
        <td>{column.spatialExtentLabel}</td>
        <td>{column.dimensionLabel || '—'}</td>
        <td><span className={`meta-tag ${column.group}`}>{GROUP_LABELS[column.group]}</span></td>
      </tr>)}</tbody>
    </table>}
  </article>;
}

export default function MetadataCatalogue() {
  const [catalogue, setCatalogue] = useState(null);
  const [error, setError] = useState(null);
  const [category, setCategory] = useState('all');
  const [query, setQuery] = useState('');

  useEffect(() => {
    let live = true;
    json(CATALOGUE_URL).then(document => live && setCatalogue(document))
      .catch(cause => live && setError(cause.message));
    return () => { live = false; };
  }, []);

  const variables = useMemo(() => {
    const term = query.trim().toLowerCase();
    return (catalogue?.variables || []).filter(variable => {
      if (category !== 'all' && variable.category !== category) return false;
      if (!term) return true;
      return [variable.label, variable.code, variable.source, variable.description]
        .some(field => String(field || '').toLowerCase().includes(term));
    });
  }, [catalogue, category, query]);

  if (error) return <main className="meta-state"><h1>The catalogue could not load.</h1><p>{error}</p></main>;
  if (!catalogue) return <main className="meta-state"><p>Loading the attribute catalogue…</p></main>;

  const scheme = catalogue.scheme;
  return <main className="meta">
    <header className="meta-head">
      <a className="meta-back" href="/"><ArrowLeft size={13}/> Map</a>
      <div>
        <span>REFERENCE METADATA</span>
        <h1>{scheme.title}</h1>
        <p>{scheme.description}</p>
      </div>
      <dl className="meta-scale">
        <div><dt>Variables</dt><dd>{count(catalogue.counts.variables)}</dd></div>
        <div><dt>Columns</dt><dd>{count(catalogue.counts.columns)}</dd></div>
        <div><dt>Basins carrying them</dt><dd>{count(catalogue.counts.basins)}</dd></div>
      </dl>
    </header>

    <section className="meta-provenance">
      <div>
        <span><Database size={11}/> Bound to</span>
        <p>{scheme.boundTo.spatialUnit} · joined on <code>{scheme.boundTo.joinKey}</code></p>
        <p className="meta-dim">{scheme.boundTo.reachJoin}.</p>
      </div>
      <div>
        <span><BookOpen size={11}/> Reference</span>
        <p>{scheme.reference}</p>
        <p className="meta-dim">Parsed from {scheme.catalogueSource}.</p>
      </div>
      <div>
        <span><ExternalLink size={11}/> Source</span>
        <p><a href={scheme.website} target="_blank" rel="noreferrer">{scheme.website}</a></p>
        <p className="meta-dim">{scheme.dataset.label}. Licences differ per variable and are listed on each card.</p>
      </div>
    </section>

    <section className="meta-groups">
      {catalogue.groups.map(group => <div key={group.id}>
        <strong>{count(group.attributeCount)}</strong>
        <span>{group.label}</span>
      </div>)}
    </section>

    <div className="meta-controls">
      <label className="meta-search">
        <Search size={13}/>
        <input value={query} onChange={event => setQuery(event.target.value)}
          placeholder="Variable, source product or code"/>
      </label>
      <div className="meta-cats">
        <button type="button" className={category === 'all' ? 'active' : ''} onClick={() => setCategory('all')}>
          <Layers size={11}/> All
        </button>
        {catalogue.categories.map(name => <button key={name} type="button"
          className={category === name ? 'active' : ''} onClick={() => setCategory(name)}>{name}</button>)}
      </div>
      <span className="meta-result-count">{count(variables.length)} of {count(catalogue.counts.variables)} variables</span>
    </div>

    <section className="meta-grid">
      {variables.map(variable => <Variable key={variable.code} variable={variable}/>)}
      {!variables.length && <p className="meta-dim">Nothing matches that filter.</p>}
    </section>

    <footer className="meta-foot">
      {catalogue.qualityNotes.map(note => <p key={note}>{note}</p>)}
    </footer>
  </main>;
}
