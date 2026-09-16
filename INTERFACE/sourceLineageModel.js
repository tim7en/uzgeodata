const dateKey = value => {
  const match = String(value || '').match(/^(\d{4})(?:-(\d{2}))?/);
  return match ? Number(match[1]) * 12 + Number(match[2] || 1) : null;
};

export const shortDate = value => String(value || '').slice(0, 10) || 'Not dated';

export function compareCoverage(sourceDate, publishedDate) {
  const source = dateKey(sourceDate), published = dateKey(publishedDate);
  if (source == null || published == null) return 'unknown';
  if (source > published) return 'source_newer';
  if (source === published) return 'aligned';
  return 'published_newer';
}

function sourceClass(check) {
  if (!check) return 'fixed_reference';
  if (check.first_image_date && check.latest_image_date) return 'continuous_collection';
  if (check.type === 'IMAGE' || check.type === 'TABLE') return 'versioned_release';
  return 'fixed_reference';
}

const maxCoverage = rows => rows.reduce((latest, row) =>
  dateKey(row.coverage_to) > dateKey(latest) ? row.coverage_to : latest, null);

export function buildEarthEngineSources(dynamicAtlas, inventory) {
  const checks = Object.fromEntries((dynamicAtlas.availability?.sources || []).map(item => [item.asset, item]));
  const byAsset = new Map();
  for (const family of dynamicAtlas.families || []) {
    if (family.acquisition !== 'Earth Engine') continue;
    for (const asset of family.assets || []) {
      if (!byAsset.has(asset)) byAsset.set(asset, {
        id: asset, title: family.source?.name || asset, provider: 'Google Earth Engine', asset,
        url: family.source?.catalogue_url, families: [], categories: new Set(), periods: new Set(),
      });
      const item = byAsset.get(asset);
      item.families.push({ id: family.family, label: family.label, category: family.category, usedPeriod: family.used_period });
      item.categories.add(family.category);
      item.periods.add(family.used_period);
    }
  }
  return [...byAsset.values()].map(item => {
    const check = checks[item.asset];
    const matchingRows = (inventory.rows || []).filter(row => row.source === item.asset || String(row.source).includes(`@${item.asset}`));
    const publishedTo = maxCoverage(matchingRows);
    return {
      ...item,
      categories: [...item.categories], periods: [...item.periods], check,
      classification: sourceClass(check), sourceLatest: check?.latest_image_date || null,
      publishedTo, comparison: compareCoverage(check?.latest_image_date, publishedTo),
      publishedVariables: matchingRows.filter(row => row.status === 'available').length,
    };
  }).sort((a, b) => a.title.localeCompare(b.title));
}

export function buildArchiveSources(dynamicAtlas) {
  const map = new Map();
  for (const family of dynamicAtlas.families || []) {
    if (family.acquisition === 'Earth Engine') continue;
    const kind = family.acquisition === 'Not fetched' ? 'direct_download' : 'local_archive';
    const id = family.source?.asset || family.source?.name || family.original?.dataset;
    if (!map.has(`${kind}:${id}`)) map.set(`${kind}:${id}`, {
      id, title: family.source?.name || family.original?.dataset || id, provider: family.source?.provider || family.acquisition,
      classification: family.acquisition === 'Not fetched' ? 'versioned_release' : 'fixed_reference',
      state: family.acquisition === 'Not fetched' ? 'not fetched' : 'available locally', families: [], kind,
      url: family.source?.catalogue_url,
    });
    map.get(`${kind}:${id}`).families.push({ id: family.family, label: family.label, category: family.category, usedPeriod: family.used_period });
  }
  return [...map.values()].sort((a, b) => a.title.localeCompare(b.title));
}

export function buildDerivedGroups(inventory) {
  return (inventory.groups || []).map(group => ({
    id: group.id, title: group.label, provider: 'UzGeoData pipeline', classification: 'derived_product',
    state: 'recomputable', intervalDays: group.interval_days, earthEngine: group.earth_engine,
    variables: (inventory.rows || []).filter(row => row.group_id === group.id), note: group.note,
  }));
}

export function buildLineage(dynamicAtlas, inventory, registry) {
  const earthEngine = buildEarthEngineSources(dynamicAtlas, inventory);
  const archives = buildArchiveSources(dynamicAtlas);
  const derived = buildDerivedGroups(inventory);
  const branches = [
    { id: 'earth_engine', label: 'Earth Engine', note: 'Catalogue assets used or assessed', items: earthEngine },
    { id: 'local', label: 'Local & provider files', note: 'Controlled snapshots and local archives', items: [...archives.filter(x => x.kind === 'local_archive'), ...(registry.local_snapshots || [])] },
    { id: 'downloads', label: 'Direct-download backlog', note: 'Known sources not fetched yet', items: archives.filter(x => x.kind === 'direct_download') },
    { id: 'external', label: 'Research datasets', note: 'Versioned datasets considered for import', items: registry.external_sources || [] },
    { id: 'derived', label: 'Recomputed outputs', note: 'Products built from upstream evidence', items: derived },
  ];
  return {
    branches,
    earthEngine,
    derived,
    counts: {
      sources: branches.reduce((sum, branch) => sum + branch.items.length, 0),
      sourceNewer: earthEngine.filter(item => item.comparison === 'source_newer').length,
      continuing: earthEngine.filter(item => item.classification === 'continuous_collection').length,
      updateGroups: derived.length,
    },
  };
}

export function filterItems(items, query, classification) {
  const needle = String(query || '').trim().toLowerCase();
  return items.filter(item => (!classification || classification === 'all' || item.classification === classification)
    && (!needle || [item.title, item.id, item.asset, item.provider, item.state,
      ...(item.families || []).flatMap(family => [family.id, family.label, family.category]),
      ...(item.variables || []).flatMap(variable => typeof variable === 'string' ? [variable] : [variable.id, variable.label]),
    ].filter(Boolean).join(' ').toLowerCase().includes(needle)));
}
