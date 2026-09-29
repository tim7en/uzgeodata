// The words a basin report uses for its data, in one place so the page, the PDF and
// the downloads say the same thing.
//
// "Observed" was the word for the TerraClimate and ERA5-Land record, and a reader
// fairly took it to mean rain gauges. Neither is a measurement at a point: both are
// gridded products, modelled from stations, satellites and reanalysis. The record is
// therefore "historical gridded data", and the months after its latest release are
// "provisional estimates", each with its source and version stated beside it.

export const RECORD = 'historical gridded data';
export const RECORD_SHORT = 'gridded record';
export const ESTIMATE = 'provisional estimate';
export const ESTIMATES = 'provisional estimates';

/** The code a CSV row carries for where its value came from. */
export const SOURCE_CODE = { observed: 'historical_gridded', estimate: 'provisional_estimate', missing: 'no_value' };

/**
 * The unit of a Sen slope over annual values.
 *
 * Extensive quantities are summed to an annual total before the slope is fitted, so
 * a precipitation trend is a change in the annual total - millimetres per year, per
 * decade - not millimetres per month. Intensive ones are averaged, and keep their
 * unit.
 */
export function trendUnit(unit, extensive) {
  const base = String(unit || '').replace(/ per month$/, '');
  return extensive ? `${base} per year, per decade` : `${base} per decade`;
}

/** What an annual trend is fitted to, in words. */
export function trendBasis(extensive) {
  return extensive ? 'annual totals' : 'annual means';
}

export const ERROR_BOUND_NOTE = 'For a period of several months the ± figure is a conservative bound: the sum '
  + 'of each estimated month’s held-out 90th-percentile absolute error. It is not a calibrated 90% interval - '
  + 'errors in neighbouring months are correlated, so they neither cancel as independent errors would nor are '
  + 'certain to add up in full.';

/**
 * The reference periods, stated apart so two numbers on different baselines are not
 * read as comparable: monthly anomalies use the years this record holds, the
 * drought index its own 1991-2020 fit on a longer record.
 */
export function baselineNote(first, last) {
  return `Two baselines are used and they are not interchangeable. Monthly normals, anomalies and percentiles `
    + `compare against ${first}–${last}, the complete years of this basin’s gridded record. The drought index, `
    + 'SPI-12, is fitted on 1991–2020 of the TerraClimate v1.1 water-year record from 1961, the WMO standard '
    + 'period. A month can be below its 2003-based normal while its water year is near normal against 1991–2020.';
}
