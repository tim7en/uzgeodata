const key = value => String(value ?? '');

export function buildReachNetwork(rivers) {
  const byId = new Map();
  const upstream = new Map();
  for (const source of rivers || []) {
    const river = {...source, id: key(source.id), nextDown: key(source.nextDown), basinId: key(source.basinId)};
    byId.set(river.id, river);
    if (!river.nextDown || river.nextDown === '0') continue;
    const children = upstream.get(river.nextDown);
    if (children) children.push(river.id);
    else upstream.set(river.nextDown, [river.id]);
  }
  for (const children of upstream.values()) {
    children.sort((left, right) => (byId.get(right)?.upstreamKm2 || 0) - (byId.get(left)?.upstreamKm2 || 0));
  }
  return {byId, upstream};
}

export function reachNeighborhood(rootId, network, options = {}) {
  const upDepth = options.upDepth ?? 5;
  const downDepth = options.downDepth ?? 5;
  const maxNodes = options.maxNodes ?? 90;
  const childrenPerNode = options.childrenPerNode ?? 4;
  const root = key(rootId);
  if (!network?.byId.has(root)) return {nodes: [], edges: []};

  const nodes = new Map([[root, {id: root, direction: 'root', depth: 0}]]);
  const edges = [];
  let frontier = [root];
  for (let depth = 1; depth <= upDepth && frontier.length && nodes.size < maxNodes; depth += 1) {
    const next = [];
    for (const parent of frontier) {
      const children = (network.upstream.get(parent) || []).slice(0, childrenPerNode);
      for (const child of children) {
        if (nodes.has(child) || nodes.size >= maxNodes) continue;
        nodes.set(child, {id: child, direction: 'upstream', depth, parent});
        edges.push({from: child, to: parent, direction: 'upstream'});
        next.push(child);
      }
    }
    frontier = next;
  }

  let current = root;
  for (let depth = 1; depth <= downDepth && nodes.size < maxNodes; depth += 1) {
    const nextDown = network.byId.get(current)?.nextDown;
    if (!nextDown || nextDown === '0' || !network.byId.has(nextDown) || nodes.has(nextDown)) break;
    nodes.set(nextDown, {id: nextDown, direction: 'downstream', depth, parent: current});
    edges.push({from: current, to: nextDown, direction: 'downstream'});
    current = nextDown;
  }
  return {nodes: [...nodes.values()], edges};
}

export function levelBasinLookup(features) {
  return new Map((features || []).map(feature => [
    key(feature.properties?.PFAF_ID), key(feature.properties?.HYBAS_ID),
  ]));
}

export function resolveLevelBasin(basin, lookup, level = 7) {
  if (!basin?.pfafId) return null;
  return lookup.get(key(basin.pfafId).slice(0, level)) || null;
}

export function anomalyTimeline(series, basinId, variable) {
  const periods = series?.basins?.[key(basinId)] || {};
  return Object.entries(periods)
    .map(([period, cells]) => {
      const cell = cells?.[variable];
      if (!cell || (!Number.isFinite(cell.z) && !Number.isFinite(cell.v))) return null;
      return {period, z: Number.isFinite(cell.z) ? cell.z : cell.v, value: cell.v, classification: cell.c || null};
    })
    .filter(Boolean)
    .sort((left, right) => left.period.localeCompare(right.period));
}

export function deviationSummary(points) {
  if (!points?.length) return {minimum: null, maximum: null, latest: null, meanAbsolute: null};
  const values = points.map(point => point.z);
  return {
    minimum: Math.min(...values),
    maximum: Math.max(...values),
    latest: points.at(-1).z,
    meanAbsolute: values.reduce((sum, value) => sum + Math.abs(value), 0) / values.length,
  };
}
