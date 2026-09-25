// The observed record ends where its source ends: TerraClimate stops in 2024-12
// and ERA5-Land reaches 2026-08. The continuation product estimates the older
// statistic from ERA for the months in between, and the producer's own 2025
// release sits beside it. Neither is an observation of the series it continues,
// and this file keeps them labelled as what they are rather than splicing them
// onto the end of the record.
//
// Variable names differ between the products because they come from different
// releases: the estimate continues `precipitation`, the 2025 producer file calls
// the same quantity `ppt`.
export const CONTINUATION_VARIABLES = {
  pre_mm_s: { estimated: 'precipitation', direct: 'ppt' },
  tmx_dc_s: { estimated: 'tmax', direct: 'tmax' },
  tmn_dc_s: { estimated: 'tmin', direct: 'tmin' },
  soil_mm_s: { estimated: 'soil', direct: 'soil' },
  aet_mm_s: { estimated: 'aet', direct: 'aet' },
  pet_mm_s: { estimated: 'pet', direct: 'pet' },
  cwd_mm_s: { estimated: 'def', direct: 'def' },
  swe_mm_s: { estimated: 'swe', direct: 'swe' },
  pds_ix_s: { estimated: 'PDSI', direct: 'PDSI' },
  rtc_mm_s: { estimated: 'q', direct: 'q' },
  vpd_kp_s: { estimated: 'vpd', direct: 'vpd' },
};

export const CONTINUATION_METHOD = 'Beyond the observed record, two separate products are shown and never '
  + 'merged into it. The estimate continues the same v1.0 statistic from ERA and carries the 90th percentile '
  + 'of its held-out absolute error, so its own uncertainty is stated in the units of the variable. The 2025 '
  + 'producer release is a different version of the source, not a later observation of the same series. '
  + 'Anomalies use the baseline of the observed record, which is what makes them comparable with it.';

const FIELD = { year: 0, month: 1, value: 2, coverage: 3, waterEquivalent: 4, errorP90: 5 };

function seriesRows(document, key) {
  const entry = document?.series?.[key];
  if (!entry?.rows?.length) return null;
  const index = (document.row_fields || []).length === 6 ? FIELD : null;
  if (!index) return null;
  return {
    label: entry.label, unit: entry.unit, product: entry.product, support: entry.support,
    rows: entry.rows
      .map(row => ({
        year: row[index.year], month: row[index.month], value: row[index.value],
        coverage: row[index.coverage], errorP90: row[index.errorP90],
      }))
      .filter(row => row.value !== null && row.value !== undefined)
      .sort((left, right) => left.year * 12 + left.month - (right.year * 12 + right.month)),
  };
}

/**
 * What the continuation holds for one variable at one spatial support.
 *
 * Returns nothing rather than something empty when a variable has no
 * continuation: ERA5-Land runoff and mean temperature already reach the present,
 * and snow cover is not continued at all.
 */
export function continuationFor(document, variable, support) {
  const names = CONTINUATION_VARIABLES[variable];
  if (!names || !document) return null;
  const estimated = seriesRows(document, `estimated_v1.0:${support}:${names.estimated}`);
  const direct = seriesRows(document, `direct_v1.1:${support}:${names.direct}`);
  if (!estimated && !direct) return null;
  return { estimated, direct };
}

/**
 * The most recent estimated month, placed against the observed baseline.
 *
 * The estimate continues the observed statistic, so the observed normals are the
 * right comparison; using the estimate's own mean would measure it against itself.
 */
export function continuationLatest(continuation, normals) {
  const series = continuation?.estimated;
  if (!series?.rows.length) return null;
  const latest = series.rows.at(-1);
  const normal = normals ? normals.byMonth[latest.month - 1] : null;
  const sample = normals ? normals.samples[latest.month - 1] : [];
  const below = sample.filter(value => value < latest.value).length;
  return {
    year: latest.year, month: latest.month, value: latest.value,
    coverage: latest.coverage, errorP90: latest.errorP90,
    unit: series.unit, label: series.label,
    months: series.rows.length,
    first: `${series.rows[0].year}-${String(series.rows[0].month).padStart(2, '0')}`,
    normal,
    anomaly: normal === null || normal === undefined ? null : latest.value - normal,
    rankPercentile: sample.length ? Math.round(100 * below / sample.length) : null,
    rankYears: sample.length,
    // An anomaly the size of the model's own error is not a signal, and a reader
    // comparing months should be told which is which.
    withinError: latest.errorP90 !== null && latest.errorP90 !== undefined && normal !== null
      && normal !== undefined && Math.abs(latest.value - normal) <= latest.errorP90,
  };
}

export function continuationCsv(continuation, support) {
  const rows = [];
  for (const [product, series] of Object.entries(continuation || {})) {
    for (const row of series?.rows || []) {
      rows.push([support, product, series.unit, row.year, row.month, row.value, row.coverage, row.errorP90]);
    }
  }
  return rows;
}

/**
 * One monthly series a reader can follow to the present.
 *
 * The observed rows stop where their source stops, and the estimate carries on
 * from there. They are joined into one series for reading and downloading, and
 * every row says which it is, because a table that ends in 2024 without saying why
 * reads as a portal two years behind - and one that continues without saying how
 * reads as observation.
 *
 * Nothing is overwritten: an estimated month is used only where the record has no
 * observation for it. The statistics elsewhere in the report - normals, anomalies,
 * the trend - are computed from the observed rows alone, which is why this returns
 * a separate series rather than extending that one.
 */
export function monthlySeries(scopeReport, continuation) {
  const observed = (scopeReport?.rows || []).map(row => ({
    year: row.year, month: row.month,
    value: row.mean_observed_area,
    coverage: row.area_coverage_percent === null || row.area_coverage_percent === undefined
      ? null : row.area_coverage_percent / 100,
    errorP90: null,
    source: row.observed_basins > 0 && row.mean_observed_area !== null ? 'observed' : null,
  }));
  const position = new Map(observed.map((row, index) => [row.year * 12 + row.month, index]));
  for (const row of continuation?.estimated?.rows || []) {
    const key = row.year * 12 + row.month;
    const entry = {
      year: row.year, month: row.month, value: row.value,
      coverage: row.coverage ?? null, errorP90: row.errorP90 ?? null, source: 'estimated_v1.0',
    };
    const index = position.get(key);
    // An observation is never replaced by an estimate of itself.
    if (index === undefined) observed.push(entry);
    else if (observed[index].source === null) observed[index] = entry;
  }
  return observed
    .filter(row => row.source !== null)
    .sort((left, right) => left.year * 12 + left.month - (right.year * 12 + right.month));
}

/**
 * One local continuation series over several basins, weighted by their area.
 *
 * Local series add up the way the observed statistics do: an area-weighted mean
 * over the basins a report matched. Upstream series do not, because two basins in
 * the same report usually share most of their catchment, and averaging those sets
 * would count the shared part twice - which is why only the local support is
 * aggregated here.
 *
 * The error reported for a month is the largest of the contributing basins', not
 * their mean: a p90 of a weighted mean is not the weighted mean of p90s, and an
 * upper bound is the one of the two that cannot mislead.
 */
export function aggregateLocalContinuation(entries, variable) {
  const months = new Map();
  let unit = null;
  let label = null;
  for (const { document, areaKm2 } of entries) {
    const series = continuationFor(document, variable, 'local')?.estimated;
    if (!series || !(areaKm2 > 0)) continue;
    unit = unit ?? series.unit;
    label = label ?? series.label;
    for (const row of series.rows) {
      const key = row.year * 12 + row.month;
      const carried = months.get(key) || { year: row.year, month: row.month, weighted: 0, area: 0, errorP90: null };
      carried.weighted += row.value * areaKm2;
      carried.area += areaKm2;
      if (row.errorP90 !== null && row.errorP90 !== undefined) {
        carried.errorP90 = Math.max(carried.errorP90 ?? 0, row.errorP90);
      }
      months.set(key, carried);
    }
  }
  if (!months.size) return null;
  const complete = entries.filter(entry => entry.areaKm2 > 0).length;
  const rows = [...months.values()]
    // A month only some of the basins carry would be a mean over a different area
    // than its neighbours, so it is left out rather than quietly rescaled.
    .filter(entry => entry.area > 0)
    .sort((left, right) => left.year * 12 + left.month - (right.year * 12 + right.month))
    .map(entry => ({ year: entry.year, month: entry.month, value: entry.weighted / entry.area,
      coverage: null, errorP90: entry.errorP90 }));
  return { estimated: { rows, unit, label, product: 'estimated_v1.0', support: 'local' }, basins: complete };
}
