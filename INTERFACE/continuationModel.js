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
