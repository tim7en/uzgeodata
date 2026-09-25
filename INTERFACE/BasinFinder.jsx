import React, { useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { formatNumber, systemMeta } from './landingModel.js';

// Search is independent of map zoom. Geometry loads only when the finder is used.
export default function BasinFinder({ entry, onSelect }) {
  const [query, setQuery] = useState('');
  const [features, setFeatures] = useState(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const requested = query.trim().length >= 3;
  useEffect(() => {
    if (!requested || !entry || features) return;
    const controller = new AbortController();
    setError('');
    fetch(entry.url, { signal: controller.signal }).then(response => {
      if (!response.ok) throw Error('Basin search could not load.');
      return response.json();
    }).then(data => setFeatures(data.features)).catch(cause => {
      if (cause.name !== 'AbortError') setError('Basin search could not load. Try again.');
    });
    return () => controller.abort();
  }, [requested, entry, features, retry]);
  const term = query.trim();
  const matches = requested && features ? features.filter(feature =>
    String(feature.properties.hybas_id).includes(term)
    || String(feature.properties.pfaf_id).includes(term)).slice(0, 6) : [];
  return <div className="land-finder">
    <h2>Find basin data</h2>
    <label className="land-search">
      <Search size={13}/>
      <input aria-label="Search basins by HYBAS or PFAF identifier" value={query}
        onChange={event => setQuery(event.target.value)} placeholder="HYBAS or PFAF id"/>
    </label>
    {!requested && <p className="land-hint">Search all level-12 basins, or select a basin on the map.</p>}
    {requested && !features && !error && <p role="status">Loading basin search…</p>}
    {error && <p role="alert">{error} <button onClick={() => setRetry(value => value + 1)}>Retry search</button></p>}
    {requested && features && !matches.length && <p role="status">No matching basin. Check the identifier.</p>}
    {!!matches.length && <div className="land-results">{matches.map(feature =>
      <div key={feature.properties.hybas_id} className="land-finder-result">
      <button type="button" onClick={() => onSelect(feature, 'history')}>
        <strong>{feature.properties.hybas_id}</strong>
        <small>{systemMeta(feature.properties.system_id).label} · {formatNumber(feature.properties.area_km2)} km²</small>
        <small>Monthly chart &amp; downloads</small>
      </button>
      <div className="land-finder-views">
        <button type="button" onClick={() => onSelect(feature, 'original')}>Attributes</button>
        <button type="button" onClick={() => onSelect(feature, 'substitutes')}>Estimates</button>
        <button type="button" onClick={() => onSelect(feature, 'catchment')}>Catchment</button>
        <button type="button" onClick={() => onSelect(feature, 'drought')}>Drought</button>
      </div>
      </div>)}</div>}
  </div>;
}
