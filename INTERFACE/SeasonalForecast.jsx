import React, { useEffect, useState } from 'react';
import { formatNumber } from './landingModel.js';
import { forecastUnits, readForecast } from './seasonalModel.js';
import './seasonalForecast.css';

const URL = '/data/atlas/seasonal-forecast/latest.json';
const share = value => `${Math.round(value * 100)}%`;
const signed = value => `${value > 0 ? '+' : ''}${Math.round(value)}`;

/**
 * Chances of a below-, near- and above-normal period, drawn as one bar.
 *
 * A forecast with no skill here is drawn grey: its probabilities are what the
 * model says, but the hindcasts show that saying it has not beaten the plain
 * 1-in-3 chances, and colouring it would suggest otherwise.
 */
export function Terciles({ probabilities, variable, useful }) {
  const parts = [['below', probabilities.below], ['near', probabilities.near], ['above', probabilities.above]];
  const names = variable === 'ppt' ? ['drier', 'near normal', 'wetter'] : ['colder', 'near normal', 'warmer'];
  return <div className={`seas-terciles seas-${variable}${useful ? '' : ' seas-unskilled'}`} role="img"
    aria-label={parts.map(([, value], index) => `${share(value)} ${names[index]}`).join(', ')}>
    {parts.map(([key, value], index) => <span key={key} className={`seas-${key}`} style={{ flexGrow: Math.max(value, 0.001) }}>
      {value >= 0.12 ? `${share(value)} ${index === 1 ? 'normal' : names[index]}` : ''}</span>)}
  </div>;
}

export function Reading({ unit, variable, window, entry }) {
  if (!entry) return null;
  const { forecast, skill } = entry;
  const precipitation = variable === 'ppt';
  const unitLabel = precipitation ? 'mm' : '°C';
  return <div className="seas-reading">
    <div className="seas-reading-head">
      <strong>{precipitation ? 'Precipitation' : 'Mean temperature'} · {window.label}</strong>
      <span className={skill.useful ? 'seas-skill seas-skill-yes' : 'seas-skill'}
        title={`Hindcasts ${skill.years} years against TerraClimate: correlation ${formatNumber(skill.correlation, 2)}, `
          + `RPSS ${formatNumber(skill.rpss, 2)}${skill.roc_below === null ? '' : `, ROC ${formatNumber(skill.roc_below, 2)}`}`}>
        {skill.useful ? 'skilful here' : 'no skill here'}</span>
    </div>
    <Terciles probabilities={forecast.probabilities} variable={variable} useful={skill.useful}/>
    <p>{precipitation
      ? <>Median {formatNumber(forecast.median, 0)} mm against a normal of {formatNumber(forecast.normal, 0)} mm
        {forecast.anomaly_percent !== null ? ` (${signed(forecast.anomaly_percent)}%)` : ''}; 80% range
        {' '}{formatNumber(forecast.p10, 0)}–{formatNumber(forecast.p90, 0)} mm.
        {' '}Chance of a drought-level {window.leads.length > 1 ? 'season' : 'month'}: <b>{share(forecast.dry_probability)}</b>
        {' '}(1 in 6 in an ordinary year).</>
      : <>Median {formatNumber(forecast.median, 1)} {unitLabel} against a normal of {formatNumber(forecast.normal, 1)} {unitLabel}
        {' '}({forecast.anomaly > 0 ? '+' : ''}{formatNumber(forecast.anomaly, 1)} {unitLabel}).</>}</p>
    {!skill.useful && <p className="seas-note">No skill here in {skill.years} years of hindcasts: read it as the
      normal range, not as a signal.</p>}
  </div>;
}

/**
 * The months ahead for the basin a reader is looking at: its level-7 basin and
 * its runoff-formation or lowland zone, from the latest SEAS5 forecast, in
 * TerraClimate's terms and with the skill it showed against TerraClimate.
 */
export default function SeasonalForecast({ basin }) {
  const [state, setState] = useState({ loading: true });
  // The accumulation season first: in these basins it is the snow that decides
  // next summer's water.
  const [period, setPeriod] = useState('season5');
  useEffect(() => {
    let live = true;
    readForecast(URL).then(forecast => live && setState({ forecast }))
      .catch(() => live && setState({ missing: true }));
    return () => { live = false; };
  }, []);
  if (state.loading || state.missing || !basin) return null;
  const { forecast } = state;
  const units = forecastUnits(forecast, basin);
  if (!units.length) return null;
  const windows = forecast.windows.filter(window => ['next3', 'season5'].includes(window.id));
  const shown = windows.find(window => window.id === period) || windows[0];
  return <section className="seas" aria-label="Seasonal forecast">
    <h4>The months ahead · seasonal forecast</h4>
    <p className="seas-meta">{forecast.system}, started {forecast.init}, {forecast.members} members. Placed in
      TerraClimate’s terms by quantile mapping against its {forecast.hindcast_years[0]}–{forecast.hindcast_years[1]}
      {' '}record, and scored against it. Precipitation and temperature only: not a river-flow forecast.</p>
    <div className="seas-periods" role="group" aria-label="Forecast period">
      {windows.map(window => <button key={window.id} type="button" aria-pressed={window.id === shown.id}
        onClick={() => setPeriod(window.id)}>{window.id === 'season5' ? `Season · ${window.label}` : `Next 3 months · ${window.label}`}</button>)}
    </div>
    {units.map(({ key, label }) => <div key={key} className="seas-unit">
      <h5>{label}</h5>
      <div className="seas-grid">{['ppt', 'tmean'].map(variable =>
        <Reading key={variable} unit={label} variable={variable} window={shown}
          entry={forecast.units[key]?.[variable]?.[shown.id]}/>)}</div>
    </div>)}
    <p className="seas-note"><a href="/seasonal.html">How SEAS5 compares with TerraClimate across the basins ↗</a></p>
  </section>;
}
