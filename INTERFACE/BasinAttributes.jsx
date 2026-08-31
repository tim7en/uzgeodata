import React, { useMemo, useState } from 'react';
import { AlertTriangle, Compass, Layers, LoaderCircle, Search, Table2 } from 'lucide-react';
import { aggregateColumn } from './basinTrace.js';

// The BasinATLAS attribute tables for a selected basin, or for everything a
// trace reached upstream of it.
//
// The tables are split by where a number comes from rather than by what it
// measures, because the two halves answer different questions and mixing them
// would be misleading:
//
//   Traced catchment  the 190 columns that describe a single sub-basin, averaged
//                     over the basins this network could actually walk. Where a
//                     catchment leaves Uzbekistan these describe the domestic
//                     part alone.
//   Full catchment    the 91 columns HydroSHEDS already integrated over the whole
//                     upstream area, border or no border. These stay true even
//                     when the trace is badly truncated, which is what makes them
//                     worth keeping apart rather than folding into one table.

const CATEGORY_ORDER = ['Hydrology', 'Physiography', 'Climate', 'Landcover', 'Soils & Geology', 'Anthropogenic'];

const SCOPES = {
  traced: {
    label: 'Traced catchment',
    hint: 'Sub-basin measurements averaged over the basins upstream, weighted by area inside Uzbekistan.',
    rules: new Set(['areaWeightedMean', 'majority']),
  },
  full: {
    label: 'Full catchment',
    hint: 'Computed by HydroSHEDS over the entire upstream area, including the part beyond the border.',
    rules: new Set(['outlet']),
  },
};

function formatValue(value, entry) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  if (typeof value !== 'number') return String(value);
  // A majority column carries a class code, so it is shown whole. Everything else
  // gets a precision that suits its size rather than a fixed one, which would
  // print a discharge of 0.003 m3/s as a flat zero.
  if (entry.aggregation === 'majority') return String(Math.round(value));
  const magnitude = Math.abs(value);
  if (magnitude === 0) return '0';
  if (magnitude >= 1000) return value.toLocaleString('en-US', { maximumFractionDigits: 0 });
  if (magnitude >= 10) return value.toFixed(1);
  if (magnitude >= 1) return value.toFixed(2);
  return value.toPrecision(2);
}

export default function BasinAttributes({ outlet, traced, attributes, dictionary, weights, loading, error }) {
  const [scope, setScope] = useState('traced');
  const [category, setCategory] = useState('Hydrology');
  const [query, setQuery] = useState('');

  const index = useMemo(
    () => (attributes ? new Map(attributes.ids.map((id, position) => [id, position])) : null),
    [attributes],
  );

  const rows = useMemo(() => {
    if (!attributes || !dictionary || !index || !outlet) return [];
    const term = query.trim().toLowerCase();
    const wanted = SCOPES[scope].rules;
    return Object.entries(dictionary)
      .filter(([, entry]) => wanted.has(entry.aggregation))
      .filter(([, entry]) => entry.category === category)
      .filter(([column, entry]) => !term
        || entry.label.toLowerCase().includes(term)
        || column.toLowerCase().includes(term))
      .map(([column, entry]) => {
        const values = attributes.values[column];
        const result = aggregateColumn(entry.aggregation, traced.ids, outlet.id, index, values, weights);
        return { column, entry, ...result };
      })
      .sort((a, b) => a.entry.label.localeCompare(b.entry.label));
  }, [attributes, dictionary, index, outlet, traced, weights, scope, category, query]);

  const counts = useMemo(() => {
    if (!dictionary) return {};
    const wanted = SCOPES[scope].rules;
    const tally = {};
    for (const entry of Object.values(dictionary)) {
      if (!wanted.has(entry.aggregation)) continue;
      tally[entry.category] = (tally[entry.category] || 0) + 1;
    }
    return tally;
  }, [dictionary, scope]);

  const categories = CATEGORY_ORDER.filter(name => counts[name]);
  const active = categories.includes(category) ? category : categories[0];
  const outletMatched = index ? index.has(outlet?.id) : false;

  if (error) return <div className="hydro-attr-empty"><AlertTriangle size={20}/><div>{error}</div></div>;
  if (loading) return <div className="hydro-attr-empty"><LoaderCircle size={20}/><div>Loading BasinATLAS attributes</div></div>;
  if (!attributes || !dictionary) return null;

  return <div className="hydro-attr">
    <div className="hydro-attr-controls">
      <div className="hydro-attr-scopes">
        {Object.entries(SCOPES).map(([key, entry]) => <button
          key={key}
          className={key === scope ? 'active' : undefined}
          onClick={() => setScope(key)}
        >{key === 'traced' ? <Layers size={12}/> : <Compass size={12}/>}{entry.label}</button>)}
      </div>
      <div className="hydro-attr-search">
        <Search size={13}/>
        <input
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="Filter attributes by name or column"
          aria-label="Filter attributes"
        />
      </div>
    </div>

    <p className="hydro-attr-hint">{SCOPES[scope].hint}</p>

    {scope === 'full' && !outletMatched && <div className="hydro-attr-warn">
      <AlertTriangle size={14}/>
      <span>
        Basin {outlet.id} is one of the {attributes.coverage.publishedBasins - attributes.coverage.matched} in
        the reference with no BasinATLAS counterpart, so the whole-catchment columns are blank for it.
        The traced-catchment table still reports the basins around it that do match.
      </span>
    </div>}

    <div className="hydro-attr-cats">
      {categories.map(name => <button
        key={name}
        className={name === active ? 'active' : undefined}
        onClick={() => setCategory(name)}
      >{name}<small>{counts[name]}</small></button>)}
    </div>

    <div className="hydro-attr-table-shell">
      <table className="hydro-attr-table">
        <thead>
          <tr>
            <th>Attribute</th>
            <th>Value</th>
            <th>Units</th>
            <th>Extent</th>
            <th>{scope === 'traced' ? 'Basins' : 'Catalog'}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => <tr key={row.column}>
            <td>
              <strong>{row.entry.label}</strong>
              <code>{row.column}</code>
            </td>
            <td className="hydro-attr-value">{formatValue(row.value, row.entry)}</td>
            <td>{row.entry.units}</td>
            <td>{row.entry.spatialExtentLabel}</td>
            <td className="hydro-attr-count">
              {scope === 'traced'
                ? (row.basins ? `${row.basins.toLocaleString()} / ${traced.ids.size.toLocaleString()}` : '—')
                : row.entry.catalogId}
            </td>
          </tr>)}
          {!rows.length && <tr><td colSpan={5} className="hydro-attr-none">
            No attributes in {active} match this filter.
          </td></tr>}
        </tbody>
      </table>
    </div>

    <div className="hydro-attr-foot">
      <Table2 size={12}/>
      <span>
        {rows.length.toLocaleString()} of {Object.keys(dictionary).length.toLocaleString()} documented
        BasinATLAS attributes &middot; decoded through the stored vocabulary
      </span>
    </div>
  </div>;
}
