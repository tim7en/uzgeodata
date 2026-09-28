// Where a basin stands now, and what its own history says about drought.
//
// Two records meet here and are kept apart. The monthly record (TerraClimate
// v1.0, observed to its source's last month, then continued by an ERA-derived
// estimate) answers "what is happening now". The drought study (TerraClimate
// v1.1, water years back to 1961) answers "how often does this basin go dry,
// and does a dry year tend to be followed by another". Neither is a forecast,
// and nothing here is presented as one.

import { mannKendall, senSlope } from './poiModel.js';

/** SPI-12 thresholds the drought study uses: moderate and severe drought years. */
export const SPI_DRY = -1;
export const SPI_SEVERE = -1.5;
// The share of a normal distribution below SPI -1, used to call a water year
// dry from its percentile when no SPI exists for it yet.
const DRY_PERCENTILE = 15.9;

const keyOf = row => row.year * 12 + row.month - 1;
const label = key => `${Math.floor(key / 12)}-${String((key % 12) + 1).padStart(2, '0')}`;
export const waterYearOf = (year, month) => (month >= 10 ? year + 1 : year);

/**
 * Mean of each calendar month over the complete observed years of a series.
 * `rows` are {year, month, value}; only complete years count, as in the report.
 */
export function normalsOf(rows) {
  const byYear = new Map();
  for (const row of rows) {
    if (row.value === null || row.value === undefined || !Number.isFinite(row.value)) continue;
    const months = byYear.get(row.year) || new Map();
    months.set(row.month, row.value);
    byYear.set(row.year, months);
  }
  const years = [...byYear.entries()].filter(([, months]) => months.size === 12).sort((a, b) => a[0] - b[0]);
  if (years.length < 10) return null;
  const samples = Array.from({ length: 12 }, (_, month) => years.map(([, months]) => months.get(month + 1)));
  return {
    firstYear: years[0][0], lastYear: years.at(-1)[0], years: years.length,
    byMonth: samples.map(values => values.reduce((total, value) => total + value, 0) / values.length),
    samples,
  };
}

// Mid-rank: in a dry month most years record nothing, and counting only the
// years strictly below would put a trace of rain in the wettest tenth.
const percentileBelow = (sample, value) => (sample.length
  ? Math.round(100 * (sample.filter(item => item < value).length
    + sample.filter(item => item === value).length / 2) / sample.length) : null);
// A percentage of a normal near zero is noise: 0.03 mm against 0.05 mm is -40%.
const MIN_PERCENT_BASE = 1;

/** 1st, 2nd, 3rd, 11th, 62nd: a percentile read aloud. */
export function ordinal(value) {
  const tens = value % 100, units = value % 10;
  const suffix = tens >= 11 && tens <= 13 ? 'th' : units === 1 ? 'st' : units === 2 ? 'nd' : units === 3 ? 'rd' : 'th';
  return `${value}${suffix}`;
}

/** Plain words for a percentile against the record, the same words for any variable. */
export function standing(percentile) {
  if (percentile === null || percentile === undefined) return null;
  if (percentile <= 10) return 'lowest tenth of the record';
  if (percentile <= 30) return 'below normal';
  if (percentile < 70) return 'near normal';
  if (percentile < 90) return 'above normal';
  return 'highest tenth of the record';
}

function contiguous(rows) {
  return rows.every((row, index) => index === 0 || keyOf(row) === keyOf(rows[index - 1]) + 1);
}

/**
 * The present, on the series a reader can follow to the latest month.
 *
 * `series` is the observed record continued by its estimate, one row a month,
 * each saying which it is ({year, month, value, source, errorP90}). The baseline
 * is always the observed record alone: an estimate measured against its own mean
 * would be measured against itself.
 *
 * Sums of estimated months carry the sum of their p90 errors - an upper bound,
 * since the errors of neighbouring months are not independent and a tighter
 * figure would claim more than the model's validation showed.
 */
export function presentConditions(series, { extensive }) {
  if (!series?.length) return null;
  const observed = series.filter(row => row.source === 'observed');
  const normals = normalsOf(observed);
  const latest = series.at(-1);
  const lastObserved = observed.at(-1) || null;
  const aggregate = values => (extensive ? values.reduce((a, b) => a + b, 0)
    : values.reduce((a, b) => a + b, 0) / values.length);
  const errorOf = rows => {
    const errors = rows.filter(row => row.source !== 'observed').map(row => row.errorP90 || 0);
    if (!errors.length) return 0;
    return extensive ? errors.reduce((a, b) => a + b, 0) : errors.reduce((a, b) => a + b, 0) / rows.length;
  };
  const percentOf = (value, normal) => (extensive && Math.abs(normal) >= MIN_PERCENT_BASE
    ? (value - normal) / normal * 100 : null);

  const monthNormal = normals ? normals.byMonth[latest.month - 1] : null;
  const month = {
    period: label(keyOf(latest)), source: latest.source, value: latest.value,
    errorP90: latest.source === 'observed' ? null : latest.errorP90 ?? null,
    normal: monthNormal,
    anomaly: monthNormal === null ? null : latest.value - monthNormal,
    anomalyPercent: monthNormal === null ? null : percentOf(latest.value, monthNormal),
    percentile: normals ? percentileBelow(normals.samples[latest.month - 1], latest.value) : null,
  };
  month.withinError = month.errorP90 !== null && month.anomaly !== null && Math.abs(month.anomaly) <= month.errorP90;
  // An estimate whose distance from normal is inside its own error has no
  // standing to report: calling it wet or dry would be reading the model's noise.
  month.standing = month.withinError ? 'not distinguishable from normal' : standing(month.percentile);

  // A window summed across a gap is a smaller number, not a drier period.
  const window = rows => {
    if (!rows.length || !contiguous(rows)) return null;
    const value = aggregate(rows.map(row => row.value));
    const normal = normals ? aggregate(rows.map(row => normals.byMonth[row.month - 1])) : null;
    return {
      from: label(keyOf(rows[0])), to: label(keyOf(rows.at(-1))), months: rows.length,
      estimatedMonths: rows.filter(row => row.source !== 'observed').length,
      value, normal, errorBound: errorOf(rows),
      anomaly: normal === null ? null : value - normal,
      anomalyPercent: normal === null ? null : percentOf(value, normal),
    };
  };

  const twelve = series.length >= 12 ? window(series.slice(-12)) : null;

  // The water year so far, October to the latest month, placed among the same
  // months of every earlier water year the observed record holds completely.
  const waterYear = waterYearOf(latest.year, latest.month);
  const start = (waterYear - 1) * 12 + 9;
  const toDate = window(series.filter(row => keyOf(row) >= start));
  if (toDate) {
    const span = keyOf(latest) - start;
    const values = new Map(observed.map(row => [keyOf(row), row.value]));
    const history = [];
    for (let year = waterYear - 1; year >= 1900; year -= 1) {
      const first = (year - 1) * 12 + 9;
      if (first < keyOf(observed[0] || latest)) break;
      const months = Array.from({ length: span + 1 }, (_, offset) => values.get(first + offset));
      if (months.every(value => value !== undefined && value !== null)) history.push(aggregate(months));
    }
    toDate.waterYear = waterYear;
    toDate.comparedYears = history.length;
    toDate.percentile = history.length >= 10 ? percentileBelow(history, toDate.value) : null;
    toDate.withinError = toDate.errorBound > 0 && toDate.anomaly !== null && Math.abs(toDate.anomaly) <= toDate.errorBound;
    toDate.standing = toDate.withinError ? 'not distinguishable from normal' : standing(toDate.percentile);
    toDate.dry = !toDate.withinError && toDate.percentile !== null && toDate.percentile <= DRY_PERCENTILE;
  }

  return {
    baseline: normals && { firstYear: normals.firstYear, lastYear: normals.lastYear, years: normals.years },
    extensive,
    lastObserved: lastObserved ? label(keyOf(lastObserved)) : null,
    latest: label(keyOf(latest)),
    estimatedMonths: series.filter(row => row.source !== 'observed' && keyOf(row) > keyOf(lastObserved || { year: 0, month: 1 })).length,
    month, lastTwelveMonths: twelve, waterYearToDate: toDate,
  };
}

/**
 * What a basin's water-year record says about drought.
 *
 * Frequencies are counts from this basin's own record, given with their counts
 * so a reader can see how few years stand behind them. The persistence figures
 * answer the question a reader asks of a dry year - does the next one tend to be
 * dry too - and are compared with the chance in any year, so a small sample that
 * merely matches the base rate is not read as a signal.
 */
export function droughtOutlook(record, support = 'local') {
  if (!record?.rows?.length) return null;
  const F = Object.fromEntries(record.fields.map((field, index) => [field, index]));
  const spiField = support === 'local' ? 'spi12' : 'up_spi12';
  const anomalyField = support === 'local' ? 'ppt_anom_pct_wmo' : 'up_ppt_anom_pct_wmo';
  if (F[spiField] === undefined) return null;
  const years = record.rows
    .map(row => ({ year: row[F.water_year], spi: row[F[spiField]], anomaly: row[F[anomalyField]],
      pdsi: support === 'local' ? row[F.pdsi] : null,
      supply: support === 'upstream' && F.up_q_anom_pct_wmo !== undefined ? row[F.up_q_anom_pct_wmo] : null }))
    .filter(row => Number.isFinite(row.spi));
  if (years.length < 20) return null;

  const frequency = (from, to) => {
    const period = years.filter(row => row.year >= from && row.year <= to);
    const dry = period.filter(row => row.spi <= SPI_DRY).length;
    const severe = period.filter(row => row.spi <= SPI_SEVERE).length;
    return { from: period[0]?.year ?? from, to: period.at(-1)?.year ?? to, years: period.length, dry, severe,
      dryShare: period.length ? dry / period.length : null, severeShare: period.length ? severe / period.length : null };
  };
  const last = years.at(-1);
  const recent = frequency(1991, last.year);
  const early = frequency(years[0].year, 1990);

  const pairs = [];
  for (let index = 1; index < years.length; index += 1) {
    if (years[index].year === years[index - 1].year + 1) pairs.push([years[index - 1], years[index]]);
  }
  const after = test => {
    const matching = pairs.filter(([previous]) => test(previous));
    const dry = matching.filter(([, next]) => next.spi <= SPI_DRY).length;
    return { years: matching.length, dry, share: matching.length ? dry / matching.length : null };
  };
  const afterDry = after(previous => previous.spi <= SPI_DRY);
  const afterOther = after(previous => previous.spi > SPI_DRY);
  const any = { years: pairs.length, dry: pairs.filter(([, next]) => next.spi <= SPI_DRY).length };
  any.share = any.years ? any.dry / any.years : null;

  let run = 0;
  for (let index = years.length - 1; index >= 0 && years[index].spi < 0; index -= 1) run += 1;

  const anomalies = years.filter(row => Number.isFinite(row.anomaly));
  let trend = null;
  if (anomalies.length >= 20) {
    const { p } = mannKendall(anomalies.map(row => row.anomaly));
    const slope = senSlope(anomalies.map(row => [row.year, row.anomaly]));
    trend = {
      from: anomalies[0].year, to: anomalies.at(-1).year, years: anomalies.length, p,
      pointsPerDecade: slope === null ? null : slope * 10,
      direction: slope === null || p >= 0.05 ? 'no detectable trend' : slope > 0 ? 'wetting' : 'drying',
    };
  }

  return {
    support, record: { from: years[0].year, to: last.year },
    last: { ...last, dry: last.spi <= SPI_DRY, severe: last.spi <= SPI_SEVERE },
    belowNormalRun: run, recent, early, afterDry, afterOther, any, trend,
  };
}

/**
 * The chance of a drought year next, from the record's persistence.
 *
 * The year it conditions on is the most recent one that can be classified: the
 * current water year when most of it has passed and its percentile against the
 * record says dry or not, otherwise the last complete year in the drought study.
 */
export function nextYearChance(outlook, toDate) {
  if (!outlook) return null;
  const useToDate = toDate && toDate.percentile !== null && toDate.months >= 9
    && toDate.waterYear > outlook.last.year;
  const dry = useToDate ? toDate.dry : outlook.last.dry;
  const basis = useToDate
    ? { waterYear: toDate.waterYear, from: 'current water year to date', months: toDate.months }
    : { waterYear: outlook.last.year, from: 'last complete water year' };
  const conditional = dry ? outlook.afterDry : outlook.afterOther;
  return {
    ...basis, dry, forWaterYear: basis.waterYear + 1,
    share: conditional.share, dryYears: conditional.dry, years: conditional.years,
    baseShare: outlook.any.share,
    // Fewer than five cases is an anecdote; say so rather than give a percentage.
    sparse: conditional.years < 5,
  };
}

export const DROUGHT_METHOD = 'Drought years are water years (October to September) with SPI-12 at or below '
  + '-1, severe at or below -1.5, from the drought study: TerraClimate v1.1 precipitation with SPI fitted on '
  + '1991-2020. Frequencies and persistence are counts from this basin\'s own record since the first water '
  + 'year in it. The chance of a drought year next is how often, in that record, a year like the latest '
  + 'was followed by a drought year - a historical frequency, not a forecast; it knows nothing of the '
  + 'coming season\'s weather. The current water year is placed by its percentile among the same months of '
  + 'every complete earlier water year in the monthly record, and is called dry at or below the 16th '
  + 'percentile, the share of years SPI -1 marks. The trend is Mann-Kendall with a Sen slope over water-year '
  + 'precipitation anomalies, in percentage points of the 1991-2020 normal per decade.';
