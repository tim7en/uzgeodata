import React, { useEffect, useState } from 'react';
import Chart from './TimeSeriesChart.jsx';
import RegressionChart from './RegressionChart.jsx';

const BASE = '/data/case-studies/';
const fmt = value => value == null ? 'Unavailable' : Number(value).toLocaleString('en', { maximumFractionDigits: 3 });
const SOIL_NOTE = 'Soil texture is modelled at 0 cm. Station soil-temperature depth is unspecified. Neither is a field soil-type survey.';

export default function RegionalStationStudy() {
  const [data, setData] = useState(null), [error, setError] = useState('');
  const [station, setStation] = useState(''), [mode, setMode] = useState('anomaly');
  const [target, setTarget] = useState('soil');
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${BASE}regional-station-study.json`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error(`Regional evidence unavailable (${response.status}).`); return response.json(); })
      .then(d => { setData(d); setStation(d.stations.find(s => d.station_relationships[s.station_id]?.soil_lst_anomaly.n >= 24)?.station_id || d.stations[0]?.station_id || ''); })
      .catch(e => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, []);
  if (error) return <section className="cs-panel" role="alert"><h2>Regional station study</h2><p>{error} The Chirchik study remains available.</p></section>;
  if (!data) return <section className="cs-panel" role="status">Loading regional station–satellite evidence…</section>;
  const site = data.stations.find(s => s.station_id === station);
  const rows = data.monthly.filter(r => r.station_id === station);
  const stats = data.audit.counts;
  const suffix = mode === 'anomaly' ? '_anomaly' : '';
  const scores = data.station_relationships[station];
  const targetKey = target === 'soil' ? 'soil_temperature_c' : 'station_air_c';
  const targetLabel = target === 'soil' ? 'Station soil temperature' : 'Station air temperature';
  return <section id="regional-study" className="cs-regional">
    <div className="cs-panel">
      <span className="cs-eyebrow">REGIONAL CASE STUDY / {data.period}</span>
      <h2>How does location shape the satellite signal?</h2>
      <p>Compare terrain, latitude, mapped soil texture and satellite surface conditions across {data.stations.length} meteorological sites. Then test whether the relationship between measured soil temperature and satellite surface temperature remains after removing the seasonal cycle.</p>
      <p className="cs-note">{data.status}. Historical window, not a current-conditions update. Site cells are not complete basin coverage.</p>
      <div className="cs-score-grid">{[[stats.monthlyValues, 'Source monthly records'], [stats.suspectValues, 'Quarantined source values'], [stats.valuesWithUnmatchedStation, 'Records awaiting identity review'], [data.network.gaugeNetwork.rows, 'Gauge / canal metadata sites']].map(([value,label]) => <div key={label}><strong>{fmt(value)}</strong><span>{label}</span></div>)}</div>
      <div className="cs-science-warning"><strong>Data quality before inference</strong><p>Placeholder station IDs no longer merge different places. Uncertain name matches are not accepted automatically. Two sheets have suspect temperature/rainfall labels. Hydrological ending years are cross-checked for Tashkent/Pskem; elsewhere dates remain inferred and do not enter date-matched comparisons. Duplicate extras: {stats.duplicateExtraRows}; conflicting month keys: {stats.conflictingDuplicateKeys}.</p><p>The gauge files add locations and metadata—not new river-discharge observations.</p></div>
    </div>
    <div className="cs-panel"><h3>1. Spatial gradients: one point per station</h3><p>Calendar months receive equal weight; each needs at least three years. Orange lines show descriptive linear fits. Spatial-block intervals reduce, but do not eliminate, the effect of nearby stations sharing climate and grid cells.</p>
      <p className="cs-note">Eligible all-season site summaries: ERA5 air {data.relationships['elevation_m:era5_air_c'].n}; daytime LST {data.relationships['elevation_m:lst_day_c'].n}; snow occurrence {data.relationships['elevation_m:snow_occurrence'].n}. Cloud-related winter gaps can prevent an annual snow summary even where a monthly series is available. No snow gradient is estimated without eligible data.</p>
      <div className="cs-analysis-grid">
        <RegressionChart rows={data.stations} xKey="elevation_m" yKey="era5_air_c" xLabel="SRTM terrain elevation (m)" yLabel="ERA5-Land air temperature (°C)" title="Terrain and modelled air temperature" scores={data.relationships['elevation_m:era5_air_c']}/>
        <RegressionChart rows={data.stations} xKey="elevation_m" yKey="lst_day_c" xLabel="SRTM terrain elevation (m)" yLabel="MODIS daytime LST (°C)" title="Terrain and satellite surface temperature" scores={data.relationships['elevation_m:lst_day_c']}/>
        <RegressionChart rows={data.stations} xKey="latitude" yKey="lst_day_c" xLabel="Latitude (°N)" yLabel="MODIS daytime LST (°C)" title="Latitude and surface temperature" scores={data.relationships['latitude:lst_day_c']}/>
        <RegressionChart rows={data.stations} xKey="elevation_m" yKey="snow_occurrence" xLabel="SRTM terrain elevation (m)" yLabel="Clear-day snow occurrence (0–1)" title="Terrain and observed snow occurrence" scores={data.relationships['elevation_m:snow_occurrence']}/>
      </div>
      <p className="cs-note">After controlling linearly for latitude and longitude, the ERA5-Land temperature–elevation coefficient is {fmt(data.location_adjusted_temperature.elevation_coefficient_c_per_km)} °C/km ({data.location_adjusted_temperature.n} sites). This is not a measured atmospheric lapse rate or an independently validated prediction.</p>
    </div>
    <div className="cs-panel"><h3>2. Mapped soil texture and vegetation</h3><p>{SOIL_NOTE} Groups below are descriptive and may differ in irrigation, elevation, land cover and latitude; they do not identify a soil effect.</p>
      {data.soil_groups.length ? <div className="cs-table-wrap"><table><thead><tr><th>USDA texture class</th><th>Sites</th><th>Median NDVI</th><th>Interquartile range</th></tr></thead><tbody>{data.soil_groups.map(g => <tr key={g.soil}><td>{g.soil}</td><td>{g.n}{g.n < 5 ? ' · sparse' : ''}</td><td>{fmt(g.median_ndvi)}</td><td>{fmt(g.q25)}–{fmt(g.q75)}</td></tr>)}</tbody></table></div> : <p>No sites meet both soil-context and all-season NDVI criteria.</p>}
    </div>
    <div className="cs-panel"><div className="cs-section-head"><div><h3>3. Separate seasonality from co-variation</h3><p>Compare raw monthly values with within-calendar-month anomalies. Six-year anomalies are study-window departures, not long-term climate anomalies.</p></div>
      <div className="cs-controls"><label>Regional station<select aria-label="Regional station" value={station} onChange={e => setStation(e.target.value)}>{data.stations.map(s => <option key={s.station_id} value={s.station_id}>{s.label}</option>)}</select></label>
      <label>Temporal comparison<select aria-label="Temporal comparison" value={mode} onChange={e => setMode(e.target.value)}><option value="anomaly">Seasonal cycle removed</option><option value="raw">Raw monthly values</option></select></label>
      <label>Station measurement<select aria-label="Station measurement" value={target} onChange={e => setTarget(e.target.value)}><option value="soil">Soil temperature</option><option value="air">Air temperature · date-checked sites only</option></select></label></div></div>
      <p className="cs-note">{site?.label} · {fmt(site?.latitude)}°N, {fmt(site?.longitude)}°E · terrain {fmt(site?.elevation_m)} m · {site?.soil_label}. {SOIL_NOTE}</p>
      <Chart rows={rows} fields={[{ key: targetKey+suffix, label: targetLabel, color: '#edb06c' }, { key: 'lst_day_c'+suffix, label: 'MODIS daytime surface temperature', color: '#58c9e5' }, { key: 'era5_air_c'+suffix, label: 'ERA5-Land air temperature', color: '#baa5ef', dashed: true }]} unit="°C" title={`${site?.label} · ${mode === 'anomaly' ? 'calendar-month departures' : 'temperature series'}`}/>
      <div className="cs-analysis-grid"><RegressionChart rows={rows} xKey={targetKey+suffix} yKey={'lst_day_c'+suffix} xLabel={`${targetLabel}${suffix ? ' anomaly' : ''} (°C)`} yLabel={`MODIS LST${suffix ? ' anomaly' : ''} (°C)`} title="Station–surface temperature relationship" scores={scores?.[`${target}_lst_${mode === 'anomaly' ? 'anomaly' : 'raw'}`]}/>
      <RegressionChart rows={rows} xKey="ndvi_anomaly" yKey="lst_day_c_anomaly" xLabel="NDVI anomaly" yLabel="Daytime LST anomaly (°C)" title="Vegetation–temperature co-variation" scores={scores?.vegetation_lst_anomaly}/></div>
      <Chart rows={rows} fields={[{key:'snow_occurrence', label:'Fraction of QA-valid days with NDSI ≥40', color:'#58c9e5'}]} unit="0–1" title={`${site?.label} · clear-day snow occurrence (not SWE)`}/>
      <p className="cs-note">MODIS endpoint land-cover classes (IGBP codes): {fmt(site?.landcover_start)} → {fmt(site?.landcover_end)}. A classification difference alone does not demonstrate land-cover change. Missing values remain gaps; satellite clear-sky sampling can be biased.</p>
    </div>
    <div className="cs-panel"><h3>Methods, provenance and downloads</h3><details><summary>Scientific methods and limits</summary><ol>{data.methods.map(method => <li key={method}>{method}</li>)}</ol></details>
      <details><summary>Station identity and unresolved source issues</summary><ul>{data.audit.unmatchedStations.map(name => <li key={name}>{name}</li>)}</ul><p>{data.audit.suspectBlockLabels.sheets.join('; ')}</p></details>
      <div className="cs-download-links">{[['regional-station-study.json','Complete study · JSON'],['regional-station-monthly.csv','Monthly values and QA counts · CSV'],['regional-station-context.csv','Coordinates, terrain and soil · CSV'],['regional-station-study.manifest.json','Methods and source hashes']].map(([file,label]) => <a key={file} href={BASE+file} download>{label}</a>)}<a href="/data/hydroclimate/regional-climate-monthly.csv" download>Raw station records and QC · CSV</a><a href="/data/hydroclimate/hydromet-gauge-network.csv" download>Gauge metadata · CSV</a></div>
      <p className="cs-note">Sources: {Object.entries(data.assets).map(([key,asset]) => <React.Fragment key={key}><a href={`https://developers.google.com/earth-engine/datasets/catalog/${asset.replaceAll('/','_')}`}>{key}</a>{' · '}</React.Fragment>)} Built {data.generated_at.slice(0,10)}. Exact retrieval times and source image IDs are retained in downloads.</p>
    </div>
  </section>;
}
