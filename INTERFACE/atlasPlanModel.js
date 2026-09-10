// The implementation plan page presents two calculators. What they compute is a
// claim about cost, so the arithmetic lives here where it can be tested rather
// than inside the component: a storage scenario is multiplication and says so,
// and a runtime estimate refuses to appear at all until a real batch has been
// measured. Neither may quietly turn a projection into a measurement.

export function clamp(value, min, max) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(max, Math.max(min, number)) : min;
}

// One row per basin, indicator and month. Revisions, methods and support
// variants are extra rows on top of this, not included here.
export function tableRows(basins, indicators, years) {
  return basins * indicators * 12 * years;
}

export function rowsPerMonth(basins, indicators) {
  return basins * indicators;
}

export function snapshotValues(basins, substitutes) {
  return basins * substitutes;
}

// A partial batch still has to run, so the count rounds up.
export function batchCount(basins, batchSize) {
  return Math.ceil(basins / batchSize);
}

// Null until a complete batch has actually been timed. Multiplying the 20-basin
// warm-cache pilot by the basin count would produce a number that looks measured
// and is not, which is the one thing this calculator must not do.
export function runtimeHours(basins, batchSize, minutesPerBatch) {
  const minutes = Number(minutesPerBatch);
  if (!Number.isFinite(minutes) || minutes <= 0) return null;
  return batchCount(basins, batchSize) * minutes / 60;
}

export function minutes(seconds) {
  return seconds / 60;
}
