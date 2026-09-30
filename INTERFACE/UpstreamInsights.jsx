import React, { useMemo } from 'react';
import { GeoJSON, MapContainer, TileLayer } from 'react-leaflet';
import { formatNumber } from './landingModel.js';
import { BASEMAPS, collectionBounds } from './mapViewModel.js';
import './upstreamInsights.css';
import { leadingGauge, responseSentence } from './upstreamModel.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const TERRAIN = BASEMAPS.find(entry => entry.id === 'terrain');
const signed = (value, digits = 0) => `${value > 0 ? '+' : ''}${digits ? formatNumber(value, digits) : Math.round(value)}`;
// Diverging: brown drier (or colder), neutral, teal wetter (or warmer).
const RAMP = ['#8c510a', '#d8b365', '#f1e3bd', '#e8ecea', '#c7eae5', '#5ab4ac', '#01665e'];

function fill(value, steps) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '#cfd8dc';
  let i = 0;
  while (i < steps.length && value > steps[i]) i += 1;
  return RAMP[i];
}

function AttributionMap({ attribution, geometry }) {
  const steps = attribution.extensive ? [-30, -15, -5, 5, 15, 30] : [-1, -0.5, -0.25, 0.25, 0.5, 1];
  const byId = useMemo(() => new Map(attribution.basins.map(b => [b.id, b])), [attribution]);
  const bounds = useMemo(() => collectionBounds(geometry.features), [geometry]);
  if (!bounds) return null;
  const style = feature => {
    const basin = byId.get(String(feature.properties.hybas_id));
    const value = attribution.extensive ? basin?.percent : basin?.anomaly;
    return { color: '#4b5d64', weight: 0.2, fillOpacity: 0.85, fillColor: fill(value, steps) };
  };
  const labels = attribution.extensive ? ['≤ −30%', '−15%', '−5%', 'near normal', '+5%', '+15%', '≥ +30%']
    : ['≤ −1 °', '−0.5 °', '−0.25 °', 'near normal', '+0.25 °', '+0.5 °', '≥ +1 °'];
  return <>
    <MapContainer className="up-map" bounds={bounds} scrollWheelZoom={false}
      dragging={!window.matchMedia?.('(pointer: coarse)').matches}>
      <TileLayer url={TERRAIN.url} attribution={TERRAIN.attribution} maxZoom={TERRAIN.maxZoom} opacity={0.6}/>
      <GeoJSON data={geometry} style={style} interactive={false}/>
    </MapContainer>
    <ul className="up-legend">{labels.map((label, i) => <li key={label}><i style={{ background: RAMP[i] }}/>{label}</li>)}</ul>
  </>;
}

function Attribution({ insights, geometry }) {
  const a = insights.attribution;
  if (!a) return null;
  const unit = a.extensive ? insights.unit.replace(/ per month$/, '') : insights.unit;
  const wetter = a.groups.filter(g => g.contribution > 0).slice(0, 5);
  const drier = a.groups.filter(g => g.contribution < 0).slice(-5).reverse();
  const row = group => <tr key={group.key}>
    <th>Level-7 basin {group.key}<small>{group.basins} sub-basin{group.basins === 1 ? '' : 's'}</small></th>
    <td>{Math.round(group.areaShare * 100)}%</td>
    <td>{group.percent === null ? `${signed(group.anomaly, 2)} ${unit}` : `${signed(group.percent)}%`}</td>
    <td>{signed(group.contribution, 1)} {a.extensive ? 'mm' : unit}</td>
  </tr>;
  return <section className="up-block">
    <h4>Contribution to the catchment-wide precipitation anomaly · water year {a.waterYear}</h4>
    <p className="up-caveat">This divides the precipitation anomaly by where it fell. It is not each sub-basin’s share of the
      change in river flow at the outlet: a high mountain sub-basin covering 10% of the area can supply far more than 10% of
      the runoff, and a lowland one far less.</p>
    <p>Across the whole upstream catchment, {insights.label} in water year {a.waterYear} (October–September) was
      {' '}{formatNumber(a.catchment.value, 0)} {unit} against a normal of {formatNumber(a.catchment.normal, 0)}
      {' '}({a.catchment.percent === null ? `${signed(a.catchment.anomaly, 2)} ${unit}` : `${signed(a.catchment.percent)}%`},
      normal {a.baseline[0]}–{a.baseline[1]}). The map shows each sub-basin’s own departure; the tables show which ranges
      moved the catchment total most, as area share × their own anomaly, so the contributions add up to the catchment figure.</p>
    <AttributionMap attribution={a} geometry={geometry}/>
    <div className="up-tables">
      {[['Pushed it wetter', wetter], ['Pushed it drier', drier]].map(([title, list]) => list.length ? <div key={title}>
        <h5>{a.extensive ? title : title.replace('wetter', 'warmer').replace('drier', 'colder')}</h5>
        <div className="poi-table"><table><thead><tr><th>Sub-basin</th><th>Area</th><th>Own anomaly</th><th>Contribution</th></tr></thead>
          <tbody>{list.map(row)}</tbody></table></div>
      </div> : null)}
    </div>
    <p className="poi-coverage">Water year {a.waterYear} is the latest one the gridded record holds completely for every
      upstream basin. Contributions are to the catchment-mean anomaly in {a.extensive ? 'mm' : unit}; a basin can be very
      anomalous and still contribute little if it is small.</p>
  </section>;
}

function Snow({ snow }) {
  if (!snow) return null;
  const recent = snow.rows.slice(-8).reverse();
  return <section className="up-block">
    <h4>Snow storage upstream</h4>
    <p>A wet winter helps next summer’s river only if it is stored as snow. For each water year: October–March
      precipitation against the snowpack it built (the largest monthly snow water equivalent), both against their
      {' '}{snow.baseline[0]}–{snow.baseline[1]} mean.{snow.snowDominated ? '' : ' Snow is a small part of this catchment’s '
      + 'winter water, so the snowpack readings carry less weight here.'}</p>
    <div className="poi-table"><table>
      <thead><tr><th>Water year</th><th>Winter precipitation</th><th>Peak snowpack</th><th>Reading</th></tr></thead>
      <tbody>{recent.map(r => <tr key={r.waterYear} title={r.statement || ''}>
        <th>{r.waterYear}</th>
        <td>{formatNumber(r.winterPrecipitation, 0)} mm{r.rainAnomaly === null ? '' : ` (${signed(r.rainAnomaly)}%)`}</td>
        <td>{formatNumber(r.peakSwe, 0)} mm{r.snowAnomaly === null ? '' : ` (${signed(r.snowAnomaly)}%)`}, {MONTHS[r.peakMonth - 1]}</td>
        <td>{r.reading}</td>
      </tr>)}</tbody>
    </table></div>
    {recent[0]?.statement && <p><b>Water year {recent[0].waterYear}:</b> {recent[0].statement}</p>}
    <p className="poi-coverage">{snow.rule}</p>
    {snow.carryNote && <p className="up-caveat">{snow.carryNote}</p>}
    <p className="poi-coverage">Snow water equivalent is TerraClimate v1.1’s modelled snowpack, not a measurement, and at
      four kilometres it smooths the high terrain the melt comes from. Satellite snow-cover persistence and freezing-level
      changes are the next additions; a peak falling earlier than usual is itself a warning sign.</p>
  </section>;
}

function Gauges({ gauges }) {
  if (!gauges) return null;
  const recent = gauges.filter(g => g.last && Number(g.last) >= 2010);
  const lead = leadingGauge(gauges);
  const answered = [lead, ...gauges.filter(g => g.response && g !== lead).sort((a, b) => b.response.n - a.response.n)].filter(Boolean);
  return <section className="up-block">
    <h4>River gauges in this catchment</h4>
    {gauges.length ? <>
      <p>{gauges.length} gauge{gauges.length === 1 ? '' : 's'} of the CA-discharge compilation lie in the upstream basins;
        {' '}{recent.length ? `${recent.length} ${recent.length === 1 ? 'has' : 'have'} a record reaching 2010 or later.`
          : 'none has a record past 2010.'} Measured discharge is what separates a meteorological drought from an actual
        shortfall in supply; these are the records a hydrological comparison would be built on.</p>
      <div className="poi-table"><table>
        <thead><tr><th>Gauge</th><th>River</th><th>Record</th><th>Mean flow</th><th>Flow vs precipitation</th></tr></thead>
        <tbody>{gauges.slice(0, 10).map(g => <tr key={g.code}>
          <th>{g.name}<small>{g.code}</small></th><td>{g.river || '—'}</td>
          <td>{g.first && g.last ? `${g.first}–${g.last}` : 'no monthly series'}</td>
          <td>{g.meanDischarge === null ? '—' : `${formatNumber(g.meanDischarge, 1)} m³/s`}</td>
          <td>{g.response?.r != null ? `r ${g.response.r.toFixed(2)} · ${g.response.n} yrs` : '—'}</td>
        </tr>)}</tbody>
      </table></div>
      {answered.slice(0, 3).map(g => <p key={g.code}>{responseSentence(g)}</p>)}
    </> : <p>No gauge of the CA-discharge compilation lies in these basins, so the precipitation here cannot yet be set
      against measured river flow.</p>}
    {answered.length ? <p className="poi-coverage">Flow against precipitation: water-year means from the CA-discharge
      records (Marti et al. 2023, CC BY 4.0) against TerraClimate v1.1 precipitation over each gauge’s own catchment.
      Most records end by 2021, so this describes how the river has responded, not this year’s flow.</p>
      : <p className="poi-coverage">No gauge here has ten water years to set against precipitation, so runoff figures for
        this catchment remain modelled generation, not measured discharge.</p>}
  </section>;
}

const km2 = value => (value < 10 ? formatNumber(value, 1) : formatNumber(Math.round(value)));

function Glaciers({ glaciers }) {
  if (!glaciers) return null;
  if (!glaciers.iceKm2) {
    return <section className="up-block"><h4>Glaciers upstream</h4>
      <p>{glaciers.assessedShare ? 'No glacier ice was mapped in the surveyed part of this catchment.'
        : 'This catchment lies outside the glacier survey, so its ice is not assessed - that is not the same as none.'}</p></section>;
  }
  const high = glaciers.iceKm2 - glaciers.below4000Km2;
  return <section className="up-block">
    <h4>Glaciers upstream</h4>
    <dl className="up-figures">
      <div><dt>Ice area</dt><dd>{km2(glaciers.iceKm2)} km²</dd></div>
      <div><dt>Share of the catchment</dt><dd>{formatNumber(glaciers.iceShare * 100, 2)}%</dd></div>
      <div><dt>Glaciers inventoried</dt><dd>{formatNumber(glaciers.glaciers)}</dd></div>
      <div><dt>Surveyed</dt><dd>{glaciers.survey ? `${glaciers.survey[0]}–${glaciers.survey[1]}` : '—'}</dd></div>
    </dl>
    <div className="up-bars-row"><span>Ice by elevation</span><div className="up-bar" role="img"
      aria-label={`${km2(glaciers.below4000Km2)} km² below 4,000 m, ${km2(high)} km² above`}>
      <span style={{ flexGrow: glaciers.below4000Km2, background: '#d8b365' }}/>
      <span style={{ flexGrow: Math.max(high, 0), background: '#8fd3ff' }}/></div></div>
    <ul className="up-legend"><li><i style={{ background: '#d8b365' }}/>below 4,000 m</li><li><i style={{ background: '#8fd3ff' }}/>4,000 m and above</li></ul>
    <p>{km2(glaciers.below4000Km2)} km² ({Math.round(glaciers.below4000Km2 / glaciers.iceKm2 * 100)}%) of the ice lies below
      4,000 m, where warming thins it first; {km2(glaciers.smallKm2)} km² is in glaciers under 0.5 km², which shrink fastest.
      Glacier melt sustains late-summer flow in dry years, so this ice is a buffer the precipitation figures above do not show.</p>
    <p className="poi-coverage">{glaciers.assessedShare < 0.99 ? `The survey covers ${Math.round(glaciers.assessedShare * 100)}% of the
      catchment, so the ice area is a floor. ` : ''}GLIMS outlines are one survey per glacier; how the ice has changed since is not
      measured here. Glacier mass change from repeat elevation surveys is the planned addition.</p>
  </section>;
}

function LandCover({ landcover }) {
  if (!landcover) return null;
  if (!landcover.coveredShare) {
    return <section className="up-block"><h4>Land cover</h4>
      <p>The annual land-cover series covers basins intersecting Uzbekistan; none of this catchment is among them yet.</p></section>;
  }
  const { years, classes, totals, change } = landcover;
  const bar = (year, y) => {
    const total = classes.reduce((sum, c) => sum + totals[y][c.code], 0) || 1;
    return <div className="up-bars-row" key={year}><span>{year}</span><div className="up-bar" role="img"
      aria-label={classes.map(c => `${c.name} ${Math.round(totals[y][c.code] / total * 100)}%`).join(', ')}>
      {classes.map(c => <span key={c.code} title={`${c.name} ${km2(totals[y][c.code])} km²`}
        style={{ flexGrow: totals[y][c.code], background: c.color }}/>)}</div></div>;
  };
  const moved = change.filter(c => Math.abs(c.change) >= 0.5).sort((a, b) => Math.abs(b.change) - Math.abs(a.change));
  const coveredText = landcover.coveredShare < 0.01 ? 'less than 1%' : `${Math.round(landcover.coveredShare * 100)}%`;
  if (!landcover.representative) {
    return <section className="up-block"><h4>Land cover</h4>
      <p>The annual land-cover series covers {coveredText} of this catchment ({km2(landcover.coveredKm2)} km²), the part
        inside Uzbekistan’s basins - too little to describe the catchment, so no composition is shown. Extending the series
        to the transboundary headwaters is planned.</p></section>;
  }
  return <section className="up-block">
    <h4>Land cover, {years[0]}–{years.at(-1)}</h4>
    <p>Annual 10 m land cover over {coveredText} of the catchment
      ({km2(landcover.coveredKm2)} km²), the part the series covers.</p>
    {bar(years[0], 0)}
    {bar(years.at(-1), years.length - 1)}
    <ul className="up-legend">{classes.filter(c => change.some(x => x.code === c.code)).map(c =>
      <li key={c.code}><i style={{ background: c.color }}/>{c.name}</li>)}</ul>
    {moved.length > 0 && <div className="poi-table"><table>
      <thead><tr><th>Class</th><th>{years[0]}</th><th>{years.at(-1)}</th><th>Change</th></tr></thead>
      <tbody>{moved.slice(0, 6).map(c => <tr key={c.code}><th>{c.name}</th><td>{km2(c.first)} km²</td><td>{km2(c.last)} km²</td>
        <td>{c.change > 0 ? '+' : ''}{km2(c.change)} km²{c.first > 0 ? ` (${c.change > 0 ? '+' : ''}${Math.round(c.change / c.first * 100)}%)` : ''}</td></tr>)}</tbody>
    </table></div>}
    <p className="poi-coverage">Impact Observatory / Esri annual land cover. Differences between single years include
      classification noise; the snow/ice class mixes seasonal snow with glaciers and is not a glacier measurement.</p>
  </section>;
}

/** The upstream catchment taken apart: anomaly by sub-basin, snow storage, and river gauges. */
export default function UpstreamInsights({ insights, geometry }) {
  if (!insights || (!insights.attribution && !insights.snow && !insights.gauges && !insights.glaciers && !insights.landcover)) return null;
  return <section className="up-insights" aria-label="Upstream catchment in detail">
    <h4 className="up-title">Upstream in detail</h4>
    <Attribution insights={insights} geometry={geometry}/>
    <Snow snow={insights.snow}/>
    <Glaciers glaciers={insights.glaciers}/>
    <LandCover landcover={insights.landcover}/>
    <Gauges gauges={insights.gauges}/>
  </section>;
}
