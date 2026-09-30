// The basin assessment: five questions a water manager asks, answered in plain
// sentences from the report's own numbers, each with what it rests on.
//
// Every sentence is conditional on the data: a figure that is missing produces
// "not established" rather than a guess, and each answer says whether it rests on
// the gridded record, provisional estimates, a forecast or nothing at all.

import { ordinal } from './droughtModel.js';
import { leadingGauge, responseSentence } from './upstreamModel.js';

const pct = value => `${Math.abs(Math.round(value))}%`;
const direction = (value, up = 'above', down = 'below') => (value >= 0 ? up : down);
const share = value => `${Math.round(value * 100)}%`;

export const BASIS = {
  gridded: 'Historical gridded data',
  provisional: 'Provisional estimates',
  forecast: 'Seasonal forecast',
  inventory: 'Survey inventory',
  gauges: 'Measured river flow (past years)',
  none: 'Not established',
};

function spiWords(spi) {
  if (spi <= -1.5) return 'a severe drought year';
  if (spi <= -1) return 'a drought year';
  if (spi >= 1) return 'a wet year';
  return 'not a drought year';
}

/** Q1: the last complete water year, precipitation against both baselines. */
function lastYear(attribution, outlook) {
  if (!attribution && !outlook) return { answer: 'Not established: no complete water year is available for this catchment.', basis: 'none' };
  const parts = [];
  if (attribution?.catchment.percent !== null && attribution?.catchment.percent !== undefined) {
    parts.push(`Water year ${attribution.waterYear} (October–September) brought ${pct(attribution.catchment.percent)} `
      + `${direction(attribution.catchment.percent, 'more', 'less')} precipitation than the ${attribution.baseline[0]}–${attribution.baseline[1]} average.`);
  }
  if (outlook?.last) {
    parts.push(`Against the longer 1991–2020 reference it was ${spiWords(outlook.last.spi)} (SPI-12 ${outlook.last.spi.toFixed(2)}).`);
    if (outlook.belowNormalRun > 1) parts.push(`It was the ${ordinal(outlook.belowNormalRun)} water year in a row below normal.`);
  }
  return { answer: parts.join(' '), basis: 'gridded' };
}

/** Q2: the current water year so far, and the latest snow season. */
function current(toDate, snow) {
  const parts = [];
  let basis = 'none';
  if (toDate) {
    parts.push(`Water year ${toDate.waterYear} so far (${toDate.from} to ${toDate.to}): precipitation is `
      + (toDate.withinError ? 'not distinguishable from normal within the estimate’s error'
        : `${toDate.anomalyPercent === null ? 'near' : `${pct(toDate.anomalyPercent)} ${direction(toDate.anomalyPercent)}`} normal`)
      + `${toDate.estimatedMonths ? `, from ${toDate.estimatedMonths} months of provisional estimates` : ''}.`);
    basis = toDate.estimatedMonths ? 'provisional' : 'gridded';
  }
  const last = snow?.rows?.at(-1);
  if (last?.statement) {
    parts.push(`In the latest complete snow season (water year ${last.waterYear}) ${last.statement.charAt(0).toLowerCase()}${last.statement.slice(1)}`
      + ` That ranks as ${last.reading}.`);
    if (basis === 'none') basis = 'gridded';
  }
  return { answer: parts.length ? parts.join(' ') : 'Not established: no current precipitation or snow figure is available.', basis };
}

/** Q3: which sub-basins made the anomaly - of precipitation, not of river flow. */
function origin(attribution) {
  if (!attribution) return { answer: 'Not established: the catchment has no upstream sub-basins to compare, or too short a record.', basis: 'none' };
  const deficit = attribution.catchment.anomaly < 0;
  const driving = attribution.groups.filter(g => (deficit ? g.contribution < 0 : g.contribution > 0))
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
  const total = driving.reduce((sum, g) => sum + Math.abs(g.contribution), 0);
  if (!driving.length || !total) return { answer: 'The anomaly was spread evenly; no sub-basin stands out.', basis: 'gridded' };
  let carried = 0, area = 0;
  const leaders = [];
  for (const group of driving) {
    leaders.push(group); carried += Math.abs(group.contribution); area += group.areaShare;
    if (carried / total >= 0.5 || leaders.length === 3) break;
  }
  const names = leaders.map(g => `${g.key} (${g.percent === null ? '' : `${g.percent > 0 ? '+' : '-'}${pct(g.percent)}`})`).join(', ');
  return { answer: `${share(carried / total)} of the catchment-wide precipitation ${deficit ? 'deficit' : 'surplus'} in water year `
    + `${attribution.waterYear} came from ${leaders.length} level-7 sub-basin${leaders.length === 1 ? '' : 's'} covering `
    + `${share(area)} of the area: ${names}. This is a share of the precipitation anomaly, not of the change in river flow - `
    + 'a high mountain sub-basin can supply far more than its area share of the runoff.', basis: 'gridded' };
}

/** Q4: the seasonal forecast, with how far it has earned trust. */
function outlookAhead(unit) {
  if (!unit?.entry) return { answer: 'Not established: no seasonal forecast is available for this catchment.', basis: 'none' };
  const { entry, label, window } = unit;
  const p = entry.forecast.probabilities;
  const wet = p.above >= p.below;
  const lead = wet ? p.above : p.below;
  const lean = `leans ${wet ? 'wetter' : 'drier'} than normal for ${window} (${share(lead)} chance)`;
  return { answer: entry.skill.useful
    ? `SEAS5 ${lean} over the ${label}, and it has beaten climatology here in past years (RPSS ${entry.skill.rpss.toFixed(2)}): `
      + `a ${wet ? 'wetter' : 'drier'} season is more likely than not. Chance of a drought-level season: ${share(entry.forecast.dry_probability)}.`
    : `SEAS5 ${lean} over the ${label}, but it has not beaten climatology here in 24 years of hindcasts: plan on the normal range.`,
  basis: 'forecast' };
}

/** Q5: river discharge - what can and cannot be said. */
function discharge(gauges, glaciers, attribution) {
  const lead = leadingGauge(gauges);
  if (lead) return withGauge(lead, gauges, glaciers, attribution);
  const parts = ['This report cannot say how much river discharge changed: it contains no measured flow and no calibrated '
    + 'runoff model, so a precipitation or snow deficit cannot yet be translated into a deficit at the river.'];
  if (gauges?.length) {
    const latest = gauges.map(g => Number(g.last)).filter(Number.isFinite).sort((a, b) => b - a)[0];
    parts.push(`${gauges.length} river gauge${gauges.length === 1 ? '' : 's'} lie in the catchment${latest ? `, with records ending by ${latest}` : ''}; `
      + 'joining their series is the next step.');
  } else if (gauges) parts.push('No gauge of the regional compilation lies in the catchment.');
  if (glaciers?.iceKm2) {
    parts.push(`Glaciers cover ${glaciers.iceKm2 < 10 ? glaciers.iceKm2.toFixed(1) : Math.round(glaciers.iceKm2)} km² of the surveyed catchment`
      + `${glaciers.assessedShare < 0.99 ? ` (${share(glaciers.assessedShare)} surveyed)` : ''}; their melt can sustain late-summer flow in a `
      + 'dry year, but their change over time is not measured here.');
  }
  return { answer: parts.join(' '), basis: 'none' };
}

/**
 * A gauge whose record answers how flow has followed precipitation. Its relation is
 * applied to the latest anomaly only when the gauge measures a large part of the
 * catchment and the relation is strong - and then as an indication, never as a figure
 * for this year's flow, which no record here measures.
 */
function withGauge(lead, gauges, glaciers, attribution) {
  const r = lead.response;
  const parts = [responseSentence(lead)];
  const share = glaciers?.area ? r.area / glaciers.area : null;
  const anomaly = attribution?.catchment.percent;
  if (r.r >= 0.6 && r.elasticity !== null && share !== null && share >= 0.25 && anomaly !== null && anomaly !== undefined) {
    const flow = anomaly * r.elasticity;
    parts.push(`The gauge measures ${Math.round(Math.min(share, 1) * 100)}% of this catchment. Had that relation held in water year `
      + `${attribution.waterYear}, its ${pct(anomaly)} precipitation ${anomaly < 0 ? 'deficit' : 'surplus'} would mean roughly `
      + `${pct(flow)} ${flow < 0 ? 'less' : 'more'} flow than average there - an indication from past years, not a measurement.`);
  }
  const latest = r.years[1];
  parts.push(`No gauge record here reaches the current year (the latest ends in ${latest}), so this year's flow is not measured.`);
  if (glaciers?.iceKm2) parts.push(`Glaciers (${glaciers.iceKm2 < 10 ? glaciers.iceKm2.toFixed(1) : Math.round(glaciers.iceKm2)} km²) can keep flow up in a dry year.`);
  return { answer: parts.join(' '), basis: 'gauges' };
}

/**
 * The five answers for a report. `scope` is 'upstream' when the catchment has more
 * than the basin itself, else 'local'.
 */
export function basinAssessment({ drought, insights, forecast }) {
  const scope = drought?.upstream ? 'upstream' : 'local';
  const reading = drought?.[scope];
  return [
    { id: 'last', question: 'What happened in the last water year?', ...lastYear(insights?.attribution, reading?.outlook) },
    { id: 'now', question: 'Where do precipitation and snow storage stand now?', ...current(reading?.toDate, insights?.snow) },
    { id: 'origin', question: 'Where did the main precipitation anomaly come from?', ...origin(insights?.attribution) },
    { id: 'forecast', question: 'What does the seasonal forecast indicate, and how reliable is it?', ...outlookAhead(forecast) },
    { id: 'flow', question: 'What can and cannot be said about river discharge?', ...discharge(insights?.gauges, insights?.glaciers, insights?.attribution) },
  ];
}
