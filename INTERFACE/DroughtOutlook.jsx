import React, { useState } from 'react';
import { formatNumber } from './landingModel.js';
import { useWidth } from './ReportChart.jsx';
import { ordinal, SPI_DRY, SPI_SEVERE } from './droughtModel.js';
import './droughtOutlook.css';

const HEIGHT = 130;
const PAD = { top: 8, right: 6, bottom: 20, left: 30 };
const share = value => (value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`);
// formatNumber gives small numbers two decimals whatever it is asked for; a
// percentage read at a glance wants whole points.
const signed = (value, digits = 1) => `${value > 0 ? '+' : ''}${digits === 0 ? Math.round(value) : formatNumber(value, digits)}`;
const ramp = spi => (spi <= -2 ? '--l-dr-d3' : spi <= SPI_SEVERE ? '--l-dr-d2' : spi <= SPI_DRY ? '--l-dr-d1'
  : spi < 1 ? '--l-dr-n0' : spi < 1.5 ? '--l-dr-w1' : spi < 2 ? '--l-dr-w2' : '--l-dr-w3');

/** SPI-12 by water year: the record the frequencies below are counted from. */
function SpiStrip({ years }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const plotWidth = Math.max(0, width - PAD.left - PAD.right);
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  const limit = Math.max(2.5, Math.ceil(Math.max(...years.map(row => Math.abs(row.spi)))));
  const y = value => PAD.top + (limit - value) / (2 * limit) * plotHeight;
  const step = plotWidth / years.length;
  const picked = hover === null ? null : years[hover];
  const every = Math.max(1, Math.ceil(years.length / Math.max(1, Math.floor(plotWidth / 44))));
  return <figure className="poi-spi">
    <div ref={ref}>{width > 0 && <svg width={width} height={HEIGHT} role="img"
      aria-label={`SPI-12 by water year, ${years[0].year} to ${years.at(-1).year}`}
      onPointerMove={event => pick(event)} onPointerDown={event => pick(event)}
      onPointerLeave={event => { if (event.pointerType === 'mouse') setHover(null); }}>
      {[SPI_DRY, SPI_SEVERE].map(level => <g key={level}>
        <line x1={PAD.left} x2={PAD.left + plotWidth} y1={y(level)} y2={y(level)} className="poi-spi-threshold"/>
        {level === SPI_DRY && <text x={PAD.left - 4} y={y(level) + 4} textAnchor="end" className="poi-chart-axis">{level}</text>}
      </g>)}
      <line x1={PAD.left} x2={PAD.left + plotWidth} y1={y(0)} y2={y(0)} className="poi-chart-grid"/>
      <text x={PAD.left - 4} y={y(0) + 4} textAnchor="end" className="poi-chart-axis">0</text>
      {years.map((row, index) => <rect key={row.year} x={PAD.left + index * step + 0.5} width={Math.max(1, step - 1)}
        y={Math.min(y(row.spi), y(0))} height={Math.max(1, Math.abs(y(row.spi) - y(0)))} rx={1}
        fill={`var(${ramp(row.spi)})`} className={hover === index ? 'poi-spi-picked' : undefined}/>)}
      {years.map((row, index) => (index % every === 0 ? <text key={row.year} x={PAD.left + (index + 0.5) * step}
        y={HEIGHT - 5} textAnchor="middle" className="poi-chart-axis">{row.year}</text> : null))}
    </svg>}</div>
    <figcaption className="poi-chart-readout">{picked
      ? <><strong>WY {picked.year}</strong> · SPI-12 {signed(picked.spi, 2)}
        {picked.spi <= SPI_SEVERE ? ' · severe drought' : picked.spi <= SPI_DRY ? ' · drought' : ''}
        {Number.isFinite(picked.anomaly) && ` · precipitation ${signed(picked.anomaly, 0)}% vs 1991–2020`}</>
      : 'Water years October–September. Brown bars are drought years (SPI-12 ≤ −1).'}</figcaption>
  </figure>;

  function pick(event) {
    const box = event.currentTarget.getBoundingClientRect();
    const index = Math.floor((event.clientX - box.left - PAD.left) / step);
    setHover(index >= 0 && index < years.length ? index : null);
  }
}

function Reading({ title, reading, unit, years }) {
  const { outlook, toDate, chance } = reading;
  const { recent, early, afterDry, any, trend, last } = outlook;
  return <section className="poi-drought-scope">
    <h5>{title}</h5>
    <SpiStrip years={years}/>
    <dl>
      {toDate && <div className={toDate.dry ? 'poi-drought-alert' : undefined}>
        <dt>Water year {toDate.waterYear} so far · {toDate.from} to {toDate.to}{toDate.estimatedMonths ? ', estimated' : ''}</dt>
        <dd>{formatNumber(toDate.value, 0)} {unit.replace(' per month', '')}
          {toDate.anomalyPercent !== null && ` · ${signed(toDate.anomalyPercent, 0)}% vs normal`}
          {toDate.percentile !== null ? ` · ${toDate.standing} (${ordinal(toDate.percentile)} percentile of ${toDate.comparedYears} years)` : ''}
          {toDate.dry ? ' · drought-level dry' : ''}</dd></div>}
      <div className={last.dry ? 'poi-drought-alert' : undefined}>
        <dt>Last complete water year, {last.year}</dt>
        <dd>SPI-12 {signed(last.spi, 2)}{last.severe ? ' · severe drought' : last.dry ? ' · drought' : ' · not a drought year'}
          {Number.isFinite(last.anomaly) && ` · ${signed(last.anomaly, 0)}% of normal precipitation`}
          {Number.isFinite(last.pdsi) && ` · PDSI ${signed(last.pdsi, 1)}`}
          {Number.isFinite(last.supply) && ` · runoff supply ${signed(last.supply, 0)}%`}</dd></div>
      {outlook.belowNormalRun > 1 && <div><dt>Below-normal run</dt>
        <dd>{outlook.belowNormalRun} water years in a row below normal (SPI-12 &lt; 0)</dd></div>}
      <div><dt>Drought years, {recent.from}–{recent.to}</dt>
        <dd>{recent.dry} of {recent.years} ({share(recent.dryShare)}), {recent.severe} severe
          {early.years ? ` · ${early.from}–${early.to}: ${early.dry} of ${early.years} (${share(early.dryShare)})` : ''}</dd></div>
      <div><dt>After a drought year</dt>
        <dd>the next was also dry in {afterDry.dry} of {afterDry.years}
          {afterDry.years >= 5 ? ` (${share(afterDry.share)})` : ''} · any year: {share(any.share)}</dd></div>
      {chance && <div className="poi-drought-chance">
        <dt>Chance of a drought year in WY {chance.forWaterYear}</dt>
        <dd>{chance.sparse
          ? `too few comparable years in the record (${chance.dryYears} of ${chance.years}) to give one`
          : `${share(chance.share)} — ${chance.dryYears} of ${chance.years} years after a `
            + `${chance.dry ? 'dry' : 'non-drought'} year were dry, against ${share(chance.baseShare)} in any year`}
          <small>Conditioned on the {chance.from} ({chance.dry ? 'dry' : 'not dry'}). A historical frequency, not a forecast.</small></dd></div>}
      {trend && <div><dt>Long-term trend, {trend.from}–{trend.to}</dt>
        <dd>{trend.direction}{trend.pointsPerDecade !== null && trend.direction !== 'no detectable trend'
          ? ` · ${signed(trend.pointsPerDecade, 1)} points of normal per decade` : ''} · p {formatNumber(trend.p, 3)}</dd></div>}
    </dl>
  </section>;
}

function yearsOf(record, support) {
  const F = Object.fromEntries(record.fields.map((field, index) => [field, index]));
  const spi = support === 'local' ? 'spi12' : 'up_spi12';
  const anomaly = support === 'local' ? 'ppt_anom_pct_wmo' : 'up_ppt_anom_pct_wmo';
  return record.rows.map(row => ({ year: row[F.water_year], spi: row[F[spi]], anomaly: row[F[anomaly]] }))
    .filter(row => Number.isFinite(row.spi) && row.year >= 1991);
}

/**
 * Drought: where the basin stands this water year, how often it goes dry, and
 * what its own record says about the year after a dry one.
 *
 * `drought` carries a reading per support ({outlook, toDate, chance}) and the
 * drought-study record each came from, so the strip is drawn from the same years
 * the counts were made from.
 */
export default function DroughtOutlook({ drought, method }) {
  if (!drought) return null;
  const scopes = [['local', 'This basin'], ['upstream', 'Everything upstream · headwater supply']]
    .filter(([scope]) => drought[scope]);
  if (!scopes.length) return null;
  return <section className="poi-drought" aria-label="Drought and outlook">
    <h4>Drought &amp; outlook</h4>
    {drought.basins > 1 && !drought.local && <p className="poi-coverage">Drought indices are fitted per basin and
      do not average, so this {drought.basins}-basin report is read through basin {drought.outlet}, which they all
      drain through, and everything upstream of it.</p>}
    <div className="poi-drought-scopes">{scopes.map(([scope, title]) => <Reading key={scope} title={title}
      reading={drought[scope]} unit={drought.unit || 'mm'} years={yearsOf(drought[scope].record, scope)}/>)}</div>
    {method && <details><summary>How drought is read</summary><p>{method}</p></details>}
  </section>;
}
