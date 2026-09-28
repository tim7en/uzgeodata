import React, { useEffect, useMemo, useState } from 'react';
import { GeoJSON, MapContainer, TileLayer } from 'react-leaflet';
import { useTheme } from './ThemeToggle.jsx';
import { formatNumber } from './landingModel.js';
import { Reading } from './SeasonalForecast.jsx';
import { BASEMAPS } from './mapViewModel.js';
import { Freshness, KeyMessages, SiteNav, SkillShareChart, VersionSection } from './SeasonalInsights.jsx';

const LATEST = '/data/atlas/seasonal-forecast/latest.json';
const SKILL = '/data/atlas/seasonal-forecast/skill.json';
const LEVEL7 = '/data/hydroclimate/reference-basins-level07.geojson';
const REPORT = '/data/atlas/climate-continuation/report.json';
const VERSIONS = '/data/atlas/climate-continuation/v1.1-vs-v1.0.json';
const SECTIONS = [['outlook', 'Outlook'], ['zones', 'Zones'], ['map', 'Map'], ['skill', 'Against TerraClimate'],
  ['terraclimate', 'TerraClimate v1.1'], ['data', 'Data & method']];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const REGIONS = [
  ['zone:amu_darya:headwater', 'Amu Darya · runoff-formation zone'],
  ['zone:syr_darya:headwater', 'Syr Darya · runoff-formation zone'],
  ['zone:amu_darya:lowland', 'Amu Darya · lowlands'],
  ['zone:syr_darya:lowland', 'Syr Darya · lowlands'],
  ['system:amu_darya', 'Amu Darya · whole system'],
  ['system:syr_darya', 'Syr Darya · whole system'],
];
const VARIABLES = [['ppt', 'Precipitation'], ['tmean', 'Mean temperature']];

const TERRAIN = BASEMAPS.find(entry => entry.id === 'terrain');

const json = url => fetch(url).then(response => (response.ok
  && (response.headers.get('content-type') || '').includes('json') ? response.json() : null)).catch(() => null);

// Which way a basin leans, and how firmly: the likelier outer tercile, on a
// diverging ramp with a neutral middle - brown drier and teal wetter for
// precipitation, blue colder and orange warmer for temperature. A season can lean
// either way, and a one-sided scale would draw a wet forecast as "not dry".
const LEAN = {
  ppt: { low: ['var(--l-dr-d1)', 'var(--l-dr-d2)', 'var(--l-dr-d3)'], high: ['var(--l-dr-w1)', 'var(--l-dr-w2)', 'var(--l-dr-w3)'],
    names: ['drier', 'wetter'] },
  tmean: { low: ['var(--sub-down)', 'var(--sub-down)', 'var(--sub-down)'], high: ['var(--sub-up)', 'var(--sub-up)', 'var(--sub-up)'],
    names: ['colder', 'warmer'] },
};
const STEPS = [0.45, 0.6, 0.75];

function lean(probabilities) {
  const low = probabilities.below >= probabilities.above;
  const value = low ? probabilities.below : probabilities.above;
  const step = STEPS.filter(threshold => value >= threshold).length;
  return { low, step };
}

function leanFill(probabilities, variable) {
  const { low, step } = lean(probabilities);
  if (!step) return { fill: 'var(--l-dr-n0)', opacity: 0.8 };
  return { fill: LEAN[variable][low ? 'low' : 'high'][step - 1], opacity: variable === 'ppt' ? 0.85 : 0.35 + 0.2 * step };
}

// Skill: nothing at or below zero (no better than climatology), then one hue
// deepening with the score.
function skillFill(rpss) {
  if (rpss === null || rpss === undefined || rpss <= 0) return 'var(--l-bg-7)';
  if (rpss < 0.1) return 'var(--l-dr-w1)';
  if (rpss < 0.2) return 'var(--l-dr-w2)';
  return 'var(--l-dr-w3)';
}

function ForecastMap({ forecast, basins, variable, period }) {
  const theme = useTheme();
  const style = feature => {
    const entry = forecast.units[`l7:${String(feature.properties.pfaf_id).slice(0, 7)}`]?.[variable]?.[period];
    if (!entry?.skill?.useful) return { color: 'var(--l-line-1)', weight: 0.4, fillOpacity: 0.3, fillColor: 'var(--l-bg-7)' };
    const { fill, opacity } = leanFill(entry.forecast.probabilities, variable);
    return { color: 'var(--l-line-1)', weight: 0.4, fillOpacity: opacity, fillColor: fill };
  };
  const tip = (feature, layer) => {
    const entry = forecast.units[`l7:${String(feature.properties.pfaf_id).slice(0, 7)}`]?.[variable]?.[period];
    if (!entry) return;
    const p = entry.forecast.probabilities;
    layer.bindTooltip(`Level-7 basin ${String(feature.properties.pfaf_id).slice(0, 7)}<br>`
      + `${Math.round(p.below * 100)}% below · ${Math.round(p.near * 100)}% near · ${Math.round(p.above * 100)}% above<br>`
      + (entry.skill.useful ? `skilful: RPSS ${formatNumber(entry.skill.rpss, 2)}` : 'no skill: read as the normal range'),
    { sticky: true });
  };
  return <MapContainer className="seas-map" center={[40.5, 68.5]} zoom={5} scrollWheelZoom={false}
    dragging={!window.matchMedia?.('(pointer: coarse)').matches}>
    {/* The atlas's own relief basemap: these are mountain catchments, and it needs no key. */}
    <TileLayer key={theme} url={TERRAIN.url} attribution={TERRAIN.attribution} maxZoom={TERRAIN.maxZoom}
      opacity={theme === 'light' ? 0.85 : 0.45}/>
    <GeoJSON key={`${variable}-${period}`} data={basins} style={style} onEachFeature={tip}/>
  </MapContainer>;
}

function SkillTable({ table, variable, period }) {
  const months = Array.from({ length: 12 }, (_, i) => i + 1);
  return <div className="seas-table"><table>
    <thead><tr><th>Start month</th>{months.map(month => <th key={month}>{MONTHS[month - 1]}</th>)}</tr></thead>
    <tbody>
      {REGIONS.map(([key, label]) => <tr key={key}><th>{label}</th>{months.map(month => {
        const score = table.skill[key]?.[variable]?.[String(month)]?.[period];
        return <td key={month} style={{ background: skillFill(score?.rpss) }} className={score?.rpss >= 0.2 ? 'seas-strong' : undefined}
          title={score ? `r ${formatNumber(score.correlation, 2)} · RPSS ${formatNumber(score.rpss, 2)}` : ''}>
          {score ? formatNumber(score.rpss, 2) : '—'}{score?.useful ? ' ✓' : ''}</td>;
      })}</tr>)}
      <tr className="seas-share"><th>Level-7 basins beating climatology</th>{months.map(month => {
        const value = table.level7_useful_share?.[variable]?.[String(month)]?.[period];
        return <td key={month}>{value === undefined ? '—' : `${Math.round(value * 100)}%`}</td>;
      })}</tr>
    </tbody>
  </table></div>;
}

function BiasTable({ table, variable }) {
  const lead = '2';
  return <div className="seas-table"><table>
    <thead><tr><th>Calendar month</th>{MONTHS.map(month => <th key={month}>{month}</th>)}</tr></thead>
    <tbody>{REGIONS.map(([key, label]) => <tr key={key}><th>{label}</th>{MONTHS.map((_, index) => {
      const cell = table.bias[key]?.[variable]?.[lead]?.[String(index + 1)];
      const text = !cell ? '—' : variable === 'ppt'
        ? (cell.ratio === null ? '—' : `×${formatNumber(cell.ratio, 2)}`)
        : `${cell.difference > 0 ? '+' : ''}${formatNumber(cell.difference, 1)}°`;
      return <td key={index} title={cell ? `SEAS5 ${cell.model} · TerraClimate ${cell.terraclimate}` : ''}>{text}</td>;
    })}</tr>)}</tbody>
  </table></div>;
}

export default function SeasonalPage() {
  const [state, setState] = useState({ loading: true });
  const [variable, setVariable] = useState('ppt');
  const [period, setPeriod] = useState('season5');
  useEffect(() => {
    // The forecast draws first; the heavier map geometry and the comparisons follow.
    json(LATEST).then(forecast => setState(current => ({ ...current, loading: false, forecast })));
    Promise.all([json(SKILL), json(REPORT), json(VERSIONS), json(LEVEL7)])
      .then(([skill, report, versions, basins]) => setState(current => ({ ...current, skill, report, versions, basins })));
  }, []);
  const windows = state.forecast?.windows || [];
  const current = windows.find(entry => entry.id === period) || windows[0];
  const headline = useMemo(() => REGIONS.slice(0, 4), []);

  return <main className="seas-page">
    <SiteNav sections={SECTIONS}/>
    <section className="seas-intro" id="outlook">
      <p className="seas-eyebrow">Seasonal forecast · Amu Darya and Syr Darya</p>
      <h1>The months ahead, and how far to trust them</h1>
      <p>ECMWF’s SEAS5 forecasts precipitation and temperature six months ahead. Here each forecast is read in the
        terms of the atlas’s own record, TerraClimate v1.1, and every statement comes with how the same forecast fared
        against TerraClimate in 24 years of hindcasts. Where it did not beat the ordinary one-in-three chances, the page
        says so and shows the normal range instead.</p>
    </section>

    {state.loading && <p role="status">Loading the latest forecast…</p>}
    {!state.loading && !state.forecast && <p className="seas-empty">No seasonal forecast is published yet. It is
      built monthly from the Copernicus Climate Data Store once the new SEAS5 run is released, on the 5th.</p>}

    {state.forecast && <>
      <KeyMessages forecast={state.forecast}/>
      <Freshness forecast={state.forecast} report={state.report}/>
      <div className="seas-controls" role="group" aria-label="Forecast shown">
        {VARIABLES.map(([id, label]) => <button key={id} type="button" aria-pressed={variable === id}
          onClick={() => setVariable(id)}>{label}</button>)}
        {windows.map(entry => <button key={entry.id} type="button" aria-pressed={period === entry.id}
          onClick={() => setPeriod(entry.id)}>{entry.label}</button>)}
      </div>
      <section className="seas-section" id="zones">
        <h2>Where the water forms, and below it</h2>
        <p className="seas-meta">{state.forecast.system}, started {state.forecast.init}, {state.forecast.members} members.
          Headwater zones are where the rivers’ water is made; this winter’s snow there is next summer’s flow.</p>
        <div className="seas-cards">{headline.map(([key, label]) => <div key={key} className="seas-card">
          <h3>{label}</h3>
          <Reading unit={label} variable={variable} window={current} entry={state.forecast.units[key]?.[variable]?.[current.id]}/>
        </div>)}</div>
      </section>

      {state.basins && <section className="seas-section" id="map">
        <h2>Basin by basin</h2>
        <p className="seas-meta">Which way {current.label} leans in each of the 438 level-7 basins: the likelier of
          {' '}{LEAN[variable].names.join(' or ')} than normal, and how likely. Grey: the forecast has shown no skill
          there, so it is no better than the normal one-in-three.</p>
        <ForecastMap forecast={state.forecast} basins={state.basins} variable={variable} period={current.id}/>
        <ul className="seas-legend">
          {[...[2, 1, 0].map(step => [`${LEAN[variable].names[0]} ${['45–60%', '60–75%', '≥ 75%'][step]}`, LEAN[variable].low[step]]),
            ['no clear lean', 'var(--l-dr-n0)'],
            ...[0, 1, 2].map(step => [`${LEAN[variable].names[1]} ${['45–60%', '60–75%', '≥ 75%'][step]}`, LEAN[variable].high[step]]),
            ['no skill', 'var(--l-bg-7)']]
            .map(([label, color]) => <li key={label}><i style={{ background: color }}/>{label}</li>)}</ul>
      </section>}
    </>}

    {state.skill && <section className="seas-section" id="skill">
      <h2>SEAS5 against TerraClimate</h2>
      <p className="seas-meta">{state.skill.start_months.length} of 12 start months evaluated.
        {state.skill.start_months.length < 12 && <> Hindcasts not yet available for{' '}
          {MONTHS.filter((_, i) => !state.skill.start_months.includes(i + 1)).join(', ')};
          their skill is unknown, not zero.</>}</p>
      <p>How much better than climatology each forecast was, as the ranked probability skill score over
        {' '}{state.skill.hindcast_years[0]}–{state.skill.hindcast_years[1]}, scored against TerraClimate v1.1 with each
        year left out of the thresholds it was judged by. Zero is no better than always forecasting one in three; ✓
        marks a score above zero with a significant correlation. The window is the one chosen above, counted from
        each start month.</p>
      <div className="seas-controls" role="group" aria-label="Skill shown">
        {VARIABLES.map(([id, label]) => <button key={id} type="button" aria-pressed={variable === id}
          onClick={() => setVariable(id)}>{label}</button>)}
        {[['next3', 'Next 3 months'], ['season5', 'Next 5 months']].map(([id, label]) =>
          <button key={id} type="button" aria-pressed={period === id} onClick={() => setPeriod(id)}>{label}</button>)}
      </div>
      <h3>When in the year a forecast is worth reading</h3>
      <p>The share of the 438 level-7 basins where the forecast beat climatology, by the month it starts.</p>
      <SkillShareChart table={state.skill} period={period}/>
      <h3>By zone and start month</h3>
      <SkillTable table={state.skill} variable={variable} period={period}/>
      <h3>How the raw model differs from the record</h3>
      <p>SEAS5’s own climate against TerraClimate’s for the same months and years, one month after the start:
        {variable === 'ppt' ? ' the ratio of precipitation totals.' : ' the difference in mean temperature.'} This is
        the bias the quantile mapping removes before any forecast above is shown; a large one in the mountains is
        expected of a one-degree model over a four-kilometre record.</p>
      <BiasTable table={state.skill} variable={variable}/>
    </section>}

    {state.versions && <section className="seas-section" id="terraclimate">
      <h2>The record underneath: TerraClimate v1.1</h2>
      <p>Every normal, anomaly and trend on the portal, and the scale the forecast is placed on, comes from TerraClimate.
        Earth Engine carries its v1.0, which stops in December 2024; the producer now publishes v1.1, built on ERA5
        anomalies, and advises against joining the two. The atlas was rebased on v1.1 from 2003 to its latest yearly
        release. What that changed, year by year, over the years both releases cover:</p>
      <VersionSection comparison={state.versions}/>
    </section>}

    <section className="seas-section seas-method" id="data">
      <h2>Data &amp; method</h2>
      <p>Monthly means of ECMWF SEAS5 (system 51) from the Copernicus Climate Data Store: 51 members for the forecast,
        25 for the 1993–2016 hindcasts. Both are reduced to the 7,445 level-12 basins by fractional overlap of the
        one-degree grid and averaged by area into level-7 basins, zones and systems; no finer unit is reported, because
        dozens of level-12 basins share a model cell. Each member’s percentile in the pooled hindcast is mapped to the
        same percentile of TerraClimate v1.1 over the same years, which puts the forecast in the record’s units and
        removes the model’s bias without inventing a relationship the hindcast does not show. A drought-level season is
        one below the 16th percentile, the share SPI −1 marks. Precipitation and temperature only: this is not a
        forecast of river flow, which also depends on the snow and ice already in the mountains.</p>
      <p>The months after TerraClimate’s latest yearly release are estimated from ERA5-Land, basin by basin and month by
        month, trained on the record’s earlier years and checked on its last six; they are marked as estimates wherever
        they appear and replaced when the producer publishes the year.</p>
      <ul className="seas-downloads">
        <li><a href="/data/atlas/seasonal-forecast/latest.json">Latest forecast, every unit (JSON)</a></li>
        <li><a href="/data/atlas/seasonal-forecast/skill.json">Skill and bias against TerraClimate (JSON)</a></li>
        <li><a href="/data/atlas/climate-continuation/v1.1-vs-v1.0.json">TerraClimate v1.1 against v1.0 (JSON)</a></li>
        <li><a href="/data/atlas/climate-continuation/report.json">Estimate validation (JSON)</a></li>
      </ul>
      <p>Basin reports carry the forecast for the basin chosen: open any basin on the <a href="/">map</a> and choose
        {' '}<b>Basin &amp; upstream report</b>, or its <b>Drought &amp; outlook</b> tab.</p>
    </section>
  </main>;
}
