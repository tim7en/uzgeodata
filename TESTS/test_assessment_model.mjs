import test from 'node:test';
import assert from 'node:assert/strict';
import { basinAssessment } from '../INTERFACE/assessmentModel.js';
import { glacierSummary, landcoverSummary } from '../INTERFACE/upstreamModel.js';

const attribution = {
  waterYear: 2025, baseline: [2004, 2025],
  catchment: { value: 380, normal: 428, anomaly: -48, percent: -11 },
  groups: [
    { key: '4619903', areaShare: 0.03, contribution: 0.5, percent: 6 },
    { key: '4619503', areaShare: 0.07, contribution: -7, percent: -16 },
    { key: '4619501', areaShare: 0.03, contribution: -4, percent: -23 },
    { key: '4619205', areaShare: 0.03, contribution: -4, percent: -24 },
    { key: '4619406', areaShare: 0.02, contribution: -3, percent: -19 },
  ],
};
const drought = { upstream: {
  outlook: { last: { spi: -0.99 }, belowNormalRun: 8 },
  toDate: { waterYear: 2026, from: '2025-10', to: '2026-08', anomalyPercent: -4, estimatedMonths: 8, withinError: false },
} };
const insights = {
  attribution,
  snow: { rows: [{ waterYear: 2025, statement: 'Winter precipitation was 6% below average, while peak modelled snow storage was 21% below average.', reading: 'near-normal winter, low snow storage' }] },
  gauges: [{ last: '2019' }, { last: '1987' }],
  glaciers: { iceKm2: 1234, assessedShare: 0.8 },
};
const forecast = { label: 'Amu Darya runoff-formation zone', window: 'Oct–Feb',
  entry: { forecast: { probabilities: { below: 0.02, near: 0.12, above: 0.86 }, dry_probability: 0 }, skill: { useful: false, rpss: 0.01 } } };

test('the assessment answers five questions from the data, each with what it rests on', () => {
  const answers = basinAssessment({ drought, insights, forecast });
  assert.deepEqual(answers.map(a => a.id), ['last', 'now', 'origin', 'forecast', 'flow']);
  const [last, now, origin, ahead, flow] = answers;
  assert.match(last.answer, /11% less precipitation than the 2004–2025 average/);
  assert.match(last.answer, /not a drought year \(SPI-12 -0\.99\)/);
  assert.match(last.answer, /8th water year in a row/);
  assert.match(now.answer, /4% below normal, from 8 months of provisional estimates/);
  assert.match(now.answer, /peak modelled snow storage was 21% below average/);
  assert.equal(now.basis, 'provisional');
  // The largest drier ranges are listed until they carry half the deficit; the wetter one is not among them.
  assert.match(origin.answer, /61% of the catchment-wide precipitation deficit in water year 2025 came from 2 level-7 sub-basins covering 10% of the area/);
  assert.match(origin.answer, /not of the change in river flow/);
  assert.match(ahead.answer, /leans wetter .* \(86% chance\).*has not beaten climatology.*normal range/);
  assert.match(flow.answer, /cannot say how much river discharge changed/);
  assert.match(flow.answer, /2 river gauges .* ending by 2019/);
  assert.match(flow.answer, /1234 km² .* \(80% surveyed\)/);
});

test('missing inputs are stated as not established, never guessed', () => {
  const answers = basinAssessment({ drought: null, insights: null, forecast: null });
  assert.ok(answers.filter(a => a.id !== 'flow').every(a => a.basis === 'none' && /Not established/.test(a.answer)));
});

test('ice is summed over surveyed basins and the surveyed share is reported', () => {
  const context = { basins: { a: [10, 5, 2, 1, [1999, 2002]], b: [0, 0, 0, 0, null] } };
  const result = glacierSummary(context, [{ id: 'a', area: 100 }, { id: 'b', area: 100 }, { id: 'c', area: 200 }]);
  assert.equal(result.iceKm2, 10);
  assert.equal(result.assessedShare, 0.5);
  assert.deepEqual(result.survey, [1999, 2002]);
  assert.equal(result.below4000Km2, 2);
});

test('land cover describes only the covered part and its change from first to last year', () => {
  const index = { years: [2017, 2025], classes: [{ code: 5, name: 'Crops' }, { code: 7, name: 'Built area' }, { code: 10, name: 'Clouds' }] };
  const series = { basins: { a: { years: { 2017: { 5: 40, 7: 5, 10: 1 }, 2025: { 5: 35, 7: 9 } } } } };
  const result = landcoverSummary(series, index, [{ id: 'a', area: 50 }, { id: 'z', area: 50 }]);
  assert.equal(result.coveredShare, 0.5);
  assert.deepEqual(result.change.map(c => [c.name, c.change]), [['Crops', -5], ['Built area', 4]]);
});
