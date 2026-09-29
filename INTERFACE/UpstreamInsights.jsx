import React, { useMemo } from 'react';
import { GeoJSON, MapContainer, TileLayer } from 'react-leaflet';
import { formatNumber } from './landingModel.js';
import { BASEMAPS, collectionBounds } from './mapViewModel.js';
import './upstreamInsights.css';

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
    <h4>Where the upstream anomaly came from · water year {a.waterYear}</h4>
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
      <tbody>{recent.map(r => <tr key={r.waterYear}>
        <th>{r.waterYear}</th>
        <td>{formatNumber(r.winterPrecipitation, 0)} mm{r.rainAnomaly === null ? '' : ` (${signed(r.rainAnomaly)}%)`}</td>
        <td>{formatNumber(r.peakSwe, 0)} mm{r.snowAnomaly === null ? '' : ` (${signed(r.snowAnomaly)}%)`}, {MONTHS[r.peakMonth - 1]}</td>
        <td>{r.reading}</td>
      </tr>)}</tbody>
    </table></div>
    <p className="poi-coverage">Snow water equivalent is TerraClimate v1.1’s modelled snowpack, not a measurement, and at
      four kilometres it smooths the high terrain the melt comes from. Satellite snow-cover persistence and freezing-level
      changes are the next additions; a peak falling earlier than usual is itself a warning sign.</p>
  </section>;
}

function Gauges({ gauges }) {
  if (!gauges) return null;
  const recent = gauges.filter(g => g.last && Number(g.last) >= 2010);
  return <section className="up-block">
    <h4>River gauges in this catchment</h4>
    {gauges.length ? <>
      <p>{gauges.length} gauge{gauges.length === 1 ? '' : 's'} of the CA-discharge compilation lie in the upstream basins;
        {' '}{recent.length ? `${recent.length} ${recent.length === 1 ? 'has' : 'have'} a record reaching 2010 or later.`
          : 'none has a record past 2010.'} Measured discharge is what separates a meteorological drought from an actual
        shortfall in supply; these are the records a hydrological comparison would be built on.</p>
      <div className="poi-table"><table>
        <thead><tr><th>Gauge</th><th>River</th><th>Record</th><th>Mean flow</th></tr></thead>
        <tbody>{gauges.slice(0, 10).map(g => <tr key={g.code}>
          <th>{g.name}<small>{g.code}</small></th><td>{g.river || '—'}</td>
          <td>{g.first && g.last ? `${g.first}–${g.last}` : 'no monthly series'}</td>
          <td>{g.meanDischarge === null ? '—' : `${formatNumber(g.meanDischarge, 1)} m³/s`}</td>
        </tr>)}</tbody>
      </table></div>
    </> : <p>No gauge of the CA-discharge compilation lies in these basins, so the precipitation here cannot yet be set
      against measured river flow.</p>}
    <p className="poi-coverage">Gauge series are not yet joined to these reports. Until they are, runoff figures in the
      atlas are modelled generation, not measured discharge.</p>
  </section>;
}

/** The upstream catchment taken apart: anomaly by sub-basin, snow storage, and river gauges. */
export default function UpstreamInsights({ insights, geometry }) {
  if (!insights || (!insights.attribution && !insights.snow && !insights.gauges)) return null;
  return <section className="up-insights" aria-label="Upstream catchment in detail">
    <h4 className="up-title">Upstream in detail</h4>
    <Attribution insights={insights} geometry={geometry}/>
    <Snow snow={insights.snow}/>
    <Gauges gauges={insights.gauges}/>
  </section>;
}
