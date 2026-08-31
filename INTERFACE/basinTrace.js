// Upstream tracing over the sub-basin network, and the arithmetic for rolling
// BasinATLAS attributes up over whatever a trace returns.
//
// The reference publishes each basin's `nextDown`, so the drainage network is
// already a tree pointing downhill. Tracing upstream means inverting it once and
// then walking outward from the chosen outlet.
//
// The one thing this file is careful about is honesty. The reference is clipped
// to Uzbekistan, so a trace from a lowland outlet returns the part of the
// catchment that lies inside the country and stops at the border — the Amu Darya
// reaches the Aral with 622,507 km² behind it, of which the clipped network can
// account for about a seventh. Every trace therefore reports what it reached
// against what HydroSHEDS says is really up there, so the difference is visible
// rather than silently folded into a total.

/** Invert `nextDown` into a map from each basin to the basins draining into it. */
export function buildUpstreamMap(basins) {
  const upstream = new Map();
  for (const basin of basins) {
    if (!basin.nextDown) continue;
    const bucket = upstream.get(basin.nextDown);
    if (bucket) bucket.push(basin.id);
    else upstream.set(basin.nextDown, [basin.id]);
  }
  return upstream;
}

/**
 * Every basin draining into `rootId`, the root included, and how many basins deep
 * the longest headwater sits.
 *
 * The walk goes one level at a time rather than depth-first, because the depth is
 * reported to the reader and a depth-first walk cannot count levels without extra
 * bookkeeping — an earlier version mixed the two and counted its own backtracking
 * as depth. Iterative either way: the Amu Darya chain runs hundreds of basins
 * deep, far enough that a recursive walk would risk the stack. `seen` also makes
 * the walk safe against a cycle, which the data should not contain but which a
 * bad rebuild could introduce.
 */
export function traceUpstream(rootId, upstream) {
  const seen = new Set([rootId]);
  let frontier = [rootId];
  let depth = 0;
  while (frontier.length) {
    const next = [];
    for (const id of frontier) {
      for (const child of upstream.get(id) || []) {
        if (seen.has(child)) continue;
        seen.add(child);
        next.push(child);
      }
    }
    if (next.length) depth += 1;
    frontier = next;
  }
  return { ids: seen, depth };
}

/**
 * What a traced set covers, measured against what should be there.
 *
 * `catchmentKm2` sums the full sub-basin areas, which is the like-for-like
 * comparison with the outlet's reported upstream area; `uzbekistanKm2` sums only
 * the parts inside the border. `coverage` is the fraction of the real catchment
 * the trace could walk — below 1 it means the headwaters leave the country, and
 * every aggregate below describes the traced part alone.
 */
export function traceCoverage(ids, records, outlet) {
  let catchmentKm2 = 0;
  let uzbekistanKm2 = 0;
  for (const id of ids) {
    const record = records.get(id);
    if (!record) continue;
    catchmentKm2 += record.areaKm2 || 0;
    uzbekistanKm2 += record.uzbekistanKm2 || 0;
  }
  const reportedKm2 = outlet?.upstreamKm2 || 0;
  return {
    basins: ids.size,
    catchmentKm2,
    uzbekistanKm2,
    reportedKm2,
    coverage: reportedKm2 > 0 ? Math.min(catchmentKm2 / reportedKm2, 1) : null,
  };
}

/**
 * Combine one attribute column over a traced set.
 *
 * The rule comes from the dictionary, which derives it from the BasinATLAS
 * suffix syntax rather than from a hand-kept list:
 *
 *   outlet            the column already integrates the whole upstream catchment,
 *                     or is measured at the pour point. Averaging it across the
 *                     set would count the headwaters once per basin they pass
 *                     through, so the outlet's own value is the answer.
 *   majority          a class code. Averaging codes yields a number that decodes
 *                     to nothing, so the class holding the most area wins.
 *   areaWeightedMean  the column describes its own sub-basin, so basins combine
 *                     in proportion to how much of them is in the country.
 *
 * Basins with no atlas match, and null values within a matched basin, drop out
 * of both the numerator and the weight — `basins` reports how many actually
 * carried a value so a thin aggregate can be spotted.
 */
export function aggregateColumn(rule, ids, outletId, index, column, weights) {
  if (rule === 'outlet') {
    const position = index.get(outletId);
    const value = position === undefined ? null : column[position];
    return { value, basins: value === null || value === undefined ? 0 : 1, rule };
  }

  if (rule === 'majority') {
    const areaByClass = new Map();
    let counted = 0;
    for (const id of ids) {
      const position = index.get(id);
      if (position === undefined) continue;
      const value = column[position];
      if (value === null || value === undefined) continue;
      areaByClass.set(value, (areaByClass.get(value) || 0) + (weights.get(id) || 0));
      counted += 1;
    }
    let best = null;
    let bestArea = -1;
    for (const [value, area] of areaByClass) {
      if (area > bestArea) { best = value; bestArea = area; }
    }
    return { value: best, basins: counted, rule };
  }

  let total = 0;
  let weight = 0;
  let counted = 0;
  for (const id of ids) {
    const position = index.get(id);
    if (position === undefined) continue;
    const value = column[position];
    if (value === null || value === undefined) continue;
    const basinWeight = weights.get(id) || 0;
    total += value * basinWeight;
    weight += basinWeight;
    counted += 1;
  }
  return { value: weight > 0 ? total / weight : null, basins: counted, rule };
}

/**
 * Which administrative units a traced catchment drains from, and how much of it
 * each one contributes.
 *
 * The overlay measured the area every basin shares with every province and
 * district, so summing that over a traced set answers the question a water
 * manager actually asks — *whose land drains to this point* — weighted by the
 * area each unit really contributes rather than by whether it happens to touch
 * the catchment. A district clipping one corner of one headwater basin ranks
 * where it belongs instead of appearing beside the province that supplies half
 * the flow.
 *
 * `sharedKm2` totals only the part of the catchment these boundaries cover, and
 * that is the denominator for `share`: upstream of the border there is no
 * administrative geography here to attribute to, so a share is a share of the
 * domestic catchment, never of the whole one.
 */
export function aggregateAdmin(ids, byBasin, level) {
  const totals = new Map();
  let sharedKm2 = 0;
  for (const id of ids) {
    const entry = byBasin[id];
    const units = entry && entry[level];
    if (!units) continue;
    for (const pcode in units) {
      const km2 = units[pcode];
      totals.set(pcode, (totals.get(pcode) || 0) + km2);
      sharedKm2 += km2;
    }
  }
  const units = [...totals.entries()]
    .map(([pcode, km2]) => ({ pcode, km2, share: sharedKm2 > 0 ? km2 / sharedKm2 : 0 }))
    .sort((a, b) => b.km2 - a.km2);
  return { units, sharedKm2 };
}
