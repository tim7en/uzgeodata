import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CircleMarker, GeoJSON, MapContainer, ScaleControl, Tooltip, useMap } from 'react-leaflet';
import { X } from 'lucide-react';
import { json, matrix } from './catchmentData.js';
import { fetchAll } from './aoiModel.js';
import { collectionBounds } from './mapViewModel.js';
import { formatNumber } from './landingModel.js';
import { MORPHOLOGY_FIELDS } from './catchmentStatisticsModel.js';
import { makePoiReport, matchPoi, MAX_UPLOAD_BYTES, parsePois, REPORT_METHOD, reportMonthlyCsv } from './poiModel.js';
import { reportFilename, reportPdf, reportZip, saveFile } from './poiExports.js';
import './damModal.css';
import './poiReport.css';

function Fit({ bounds }) {
  const map = useMap();
  useEffect(() => {
    const fit = () => { map.invalidateSize(); map.fitBounds(bounds, { padding: [16, 16], maxZoom: 12, animate: false }); };
    const observer = new ResizeObserver(fit); observer.observe(map.getContainer()); fit();
    return () => observer.disconnect();
  }, [map, bounds]);
  return null;
}

function ReportMap({ report }) {
  const bounds = useMemo(() => {
    const result = collectionBounds([...report.upstream_geometry.features, report.input]);
    if (result && report.input.geometry.type === 'Point') {
      const [lon, lat] = report.input.geometry.coordinates;
      result[0] = [Math.min(result[0][0], lat), Math.min(result[0][1], lon)];
      result[1] = [Math.max(result[1][0], lat), Math.max(result[1][1], lon)];
    }
    return result;
  }, [report]);
  if (!bounds) return null;
  const coordinate = report.input.geometry.type === 'Point' ? report.input.geometry.coordinates : null;
  return <>
    <MapContainer className="poi-map" bounds={bounds} preferCanvas scrollWheelZoom={false}>
      <GeoJSON data={report.upstream_geometry} interactive={false} style={{ color: '#1594bc', weight: 0.6, fillOpacity: 0.25 }}/>
      <GeoJSON data={report.local_geometry} interactive={false} style={{ color: '#df7300', weight: 2, fillOpacity: 0.6 }}/>
      {coordinate ? <CircleMarker center={[coordinate[1], coordinate[0]]} radius={6}
        pathOptions={{ color: '#6326a3', fillColor: '#e2baff', fillOpacity: 1 }}><Tooltip>Uploaded point</Tooltip></CircleMarker>
        : <GeoJSON data={report.input} interactive={false} style={{ color: '#6326a3', weight: 3, fill: false }}/>}
      {report.match.status === 'snapped' && <CircleMarker center={[report.match.snapped_coordinate[1], report.match.snapped_coordinate[0]]}
        radius={4} pathOptions={{ color: '#cf4317', fillOpacity: 1 }}><Tooltip>Snapped basin boundary</Tooltip></CircleMarker>}
      <Fit bounds={bounds}/><ScaleControl imperial={false}/>
    </MapContainer>
    <p className="poi-map-key">Orange: matched basins · Blue: upstream · Purple: uploaded location</p>
  </>;
}

function AttributeDetails({ report }) {
  const [open, setOpen] = useState(false), [selected, setSelected] = useState(0);
  const record = report.records[selected] || report.records[0];
  return <details onToggle={event => setOpen(event.currentTarget.open)}><summary>Matched basin attributes</summary>
    {open && <>
      <p>Original HydroATLAS values and project estimates retain their own units and periods. Upstream attributes must not be summed across basins.</p>
      <label className="poi-picker">Attribute basin<select value={selected} onChange={event => setSelected(Number(event.target.value))}>
        {report.records.map((item, i) => <option value={i} key={item.basin_id}>Basin {item.basin_id}</option>)}
      </select></label>
      <div className="poi-table"><table><thead><tr><th>Attribute</th><th>HydroATLAS</th><th>Estimate</th></tr></thead>
        <tbody>{report.catalogue.attributes.map((key, i) => {
          const meta = report.catalogue.meta[key];
          return <tr key={key}><th>{meta?.label || key}<small>{key}</small></th>
            <td>{record.original[i] === -9999 ? 'Not reported' : formatNumber(record.original[i], 2)} <small>{meta?.unit} · {meta?.original?.period}</small></td>
            <td>{formatNumber(record.substitute?.[i], 2)} <small>{meta?.substitute?.unit} · {meta?.substitute?.period?.join(' – ')}</small></td></tr>;
        })}</tbody>
      </table></div>
    </>}
  </details>;
}

function Summary({ report, scope }) {
  const data = report[scope];
  const latest = data.rows.findLast(row => row.observed_basins > 0);
  return <section className="poi-summary">
    <h3>{scope === 'local' ? 'Local basin' : 'Upstream including local'}</h3>
    <p>{formatNumber(data.ids.length)} basins · {formatNumber(data.areaKm2, 2)} km²</p>
    {latest ? <>
      <p>Latest available: {latest.year}-{String(latest.month).padStart(2, '0')}</p>
      <strong>{formatNumber(latest.mean_observed_area, 2)} {report.meta.unit}</strong>
      <p>Area-weighted mean · {formatNumber(latest.area_coverage_percent, 1)}% area coverage</p>
      <p>{data.total.label}: {latest.total_full_catchment == null ? 'Not available' : `${formatNumber(latest.total_full_catchment, 2)} ${data.total.unit}`}</p>
    </> : <p>No observations for this variable.</p>}
  </section>;
}

export default function PoiReportModal({ entry, drawn, basinId, onClose }) {
  const [data, setData] = useState(null), [upload, setUpload] = useState(null);
  const [matches, setMatches] = useState([]), [active, setActive] = useState(0);
  const [tolerance, setTolerance] = useState(1), [variable, setVariable] = useState('pre_mm_s');
  const [report, setReport] = useState(null), [error, setError] = useState('');
  const [inputError, setInputError] = useState('');
  const [loadError, setLoadError] = useState(''), [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(''), [matching, setMatching] = useState(false), [loadingReport, setLoadingReport] = useState(false);
  const card = useRef(null), fileVersion = useRef(0), records = useRef(new Map());
  useEffect(() => {
    const previous = document.activeElement;
    card.current.querySelector('button').focus();
    const keydown = event => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); }
      if (event.key === 'Tab') {
        const controls = [...card.current.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href], summary')]
          .filter(el => el.getClientRects().length);
        const first = controls[0], last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', keydown);
    return () => { fileVersion.current++; document.removeEventListener('keydown', keydown); if (previous?.isConnected) previous.focus(); };
  }, [onClose]);

  useEffect(() => {
    if (!entry) return;
    const controller = new AbortController(); const signal = controller.signal;
    setLoadError(''); setData(null);
    Promise.all([json(entry.url, signal), json('/data/atlas/catchments/index.json', signal), json('/data/atlas/catalogue.json', signal)])
      .then(async ([geometry, index, catalogue]) => {
        const morphology = await json(index.morphology_url, signal);
        if (!signal.aborted) setData({ geometry, index, catalogue, morphology });
      }).catch(cause => { if (!signal.aborted) setLoadError(cause.message); });
    return () => controller.abort();
  }, [entry, retry]);

  // A basin the reader picked on the map is not matched to anything: it is the
  // answer already. Running its own outline back through polygon intersection
  // would pull in every neighbour that shares a boundary with it.
  useEffect(() => {
    if (!basinId || !data) return;
    const feature = data.geometry.features.find(item => String(item.properties.hybas_id) === String(basinId)
      && Number(item.properties.basin_level) === 12);
    if (!feature) { setInputError(`Basin ${basinId} has no published level-12 outline.`); return; }
    const name = `Basin ${basinId}`;
    setInputError(''); setError(''); setActive(0);
    setUpload({ name, collection: { type: 'FeatureCollection',
      features: [{ ...feature, id: 1, properties: { ...feature.properties, poi_name: name } }] } });
    setMatches([{ status: 'selected on the map', basins: [feature], distanceKm: null, coordinate: null }]);
  }, [basinId, data]);

  useEffect(() => {
    if (basinId) return undefined;
    let live = true; setMatches([]); setReport(null); setMatching(false);
    if (!upload || !data) return;
    setMatching(true); setError('');
    (async () => {
      const results = [];
      for (const feature of upload.collection.features) {
        await new Promise(resolve => setTimeout(resolve, 0));
        if (!live) return;
        results.push(matchPoi(feature, data.geometry.features, tolerance));
      }
      if (live) { setMatches(results); setMatching(false); }
    })().catch(cause => { if (live) { setError(cause.message); setMatching(false); } });
    return () => { live = false; };
  }, [data, upload, tolerance]);

  useEffect(() => {
    const match = matches[active];
    setReport(null); setError(''); setLoadingReport(false);
    if (!match?.basins.length || !data) return;
    if (match.basins.length > 100) { setError('This polygon intersects more than 100 basins. Upload a smaller polygon to create its report.'); return; }
    const controller = new AbortController(); const signal = controller.signal;
    setLoadingReport(true);
    (async () => {
      const values = await matrix(data.index, variable, signal);
      const missing = match.basins.map(f => String(f.properties.hybas_id)).filter(id => !records.current.has(id));
      const { results, failures } = await fetchAll(missing.map(id => `/data/atlas/basins/${id}.json`), {
        fetcher: url => fetch(url, { signal }), concurrency: 6,
      });
      if (signal.aborted) return;
      if (failures.length) throw Error('Some basin attribute files could not load. Retry to produce a complete report.');
      results.forEach((record, i) => records.current.set(missing[i], record));
      const result = makePoiReport({ feature: upload.collection.features[active], match, ...data, values, variable, sourceFile: upload.name });
      setReport({ ...result, catalogue: data.catalogue, records: result.local.ids.map(id => records.current.get(id)) });
    })().catch(cause => { if (!signal.aborted) setError(cause.message); })
      .finally(() => { if (!signal.aborted) setLoadingReport(false); });
    return () => controller.abort();
  }, [data, upload, matches, active, variable, retry]);

  // An area drawn on the map is the same kind of input as an uploaded polygon, so
  // it goes through the same parser: one validation path, one set of error
  // messages, and a ring that failed to close is caught here rather than deep in
  // the matching.
  useEffect(() => {
    if (!drawn || basinId) return;
    const version = ++fileVersion.current;
    setInputError(''); setError(''); setReport(null); setMatches([]); setActive(0);
    try {
      const collection = parsePois(JSON.stringify(drawn), 'drawn-area.geojson');
      if (version === fileVersion.current) setUpload({ name: 'Area drawn on the map', collection });
    } catch (cause) { if (version === fileVersion.current) setInputError(cause.message); }
  }, [drawn]);

  const readFile = async event => {
    const file = event.target.files[0]; event.target.value = '';
    if (!file) return;
    const version = ++fileVersion.current;
    setInputError(''); setError(''); setReport(null); setUpload(null); setMatches([]); setActive(0);
    try {
      if (file.size > MAX_UPLOAD_BYTES) throw Error('Files must be 5 MB or smaller.');
      const collection = parsePois(await file.text(), file.name);
      if (version === fileVersion.current) setUpload({ name: file.name, collection });
    } catch (cause) { if (version === fileVersion.current) setInputError(cause.message); }
  };
  const download = async kind => {
    setBusy(kind); setError('');
    try {
      const name = reportFilename(report);
      if (kind === 'PDF') saveFile(`${name}.pdf`, await reportPdf(report), 'application/pdf');
      if (kind === 'ZIP') saveFile(`${name}.zip`, await reportZip(report), 'application/zip');
      if (kind === 'CSV') saveFile(`${name}.csv`, reportMonthlyCsv(report), 'text/csv;charset=utf-8');
      if (kind === 'JSON') saveFile(`${name}.json`, JSON.stringify(report, null, 2), 'application/json');
    } catch (cause) { setError(cause.message); } finally { setBusy(''); }
  };
  const match = matches[active];
  return <div className="dam-modal poi-modal" role="dialog" aria-modal="true" aria-labelledby="poi-title" onClick={onClose}>
    <div className="dam-modal-card" ref={card} onClick={event => event.stopPropagation()}>
      <button type="button" className="dam-modal-close" aria-label="Close" onClick={onClose}><X size={16}/></button>
      <header><span className="dam-modal-kicker">Basin atlas · Your locations</span><h2 id="poi-title">Upload &amp; basin reports</h2>
        <p className="dam-modal-sub">Match points or polygons to level-12 basins and compare local and upstream information.</p></header>
      <div className="poi-controls">
        <label>{drawn || basinId ? 'Upload other locations' : 'Upload locations'}
          <input type="file" accept=".geojson,.json,.csv" onChange={readFile} disabled={!!busy}/></label>
        {!basinId && <label>Maximum point snap distance
          <select value={tolerance} disabled={!!busy} onChange={event => setTolerance(Number(event.target.value))}>
            {[0, 0.1, 0.5, 1, 2, 5, 10].map(km => <option key={km} value={km}>{km ? `${km} km` : 'Containing basin only'}</option>)}
          </select>
        </label>}
      </div>
      {basinId && <p role="status">Reporting on basin {basinId}, chosen on the map, and everything
        draining into it. Upload a file to report on something else.</p>}
      {drawn && <p role="status">Reporting on the area drawn on the map. Its statistics describe every
        level-12 basin the area intersects, whole, not the drawn shape itself. Upload a file to report on
        something else.</p>}
      <p>GeoJSON Point, Polygon or MultiPolygon; or CSV with longitude, latitude and optional name columns. WGS84 coordinates. Up to 100 locations, 5 MB. Files stay in your browser.</p>
      <p>Points outside a basin snap to its nearest boundary only within the chosen distance. Polygons use all intersecting basins.</p>
      {!data && !loadError && <p role="status">Loading basin boundaries and statistics index…</p>}
      {loadError && <p role="alert">{loadError} <button onClick={() => setRetry(n => n + 1)}>Retry loading</button></p>}
      {inputError && <p role="alert">{inputError}</p>}
      {error && <p role="alert">{error} {upload && <button onClick={() => setRetry(n => n + 1)}>Retry report</button>}</p>}
      {matching && <p role="status">Matching uploaded locations…</p>}
      {upload && <label className="poi-picker">Location report
        <select value={active} disabled={matching || !!busy} onChange={event => setActive(Number(event.target.value))}>
          {upload.collection.features.map((feature, i) => <option key={feature.id} value={i}>{i + 1}. {feature.properties.poi_name} · {matches[i]?.status || 'pending'}</option>)}
        </select>
      </label>}
      {match && <p>Match: <strong>{match.status}</strong>{match.distanceKm != null && ` · ${formatNumber(match.distanceKm, 3)} km`}
        {match.basins.length > 0 && ` · ${match.basins.length} basin(s)`}</p>}
      {match?.status === 'unmatched' && <p role="status">No basin matches this location within the selected rule. Check the coordinates or point snap distance. No report has been inferred.</p>}
      {data && upload && <label className="poi-picker">Report variable
        <select value={variable} disabled={!!busy} onChange={event => setVariable(event.target.value)}>
          {Object.entries(data.index.series).map(([key, item]) => <option key={key} value={key}>{item.meta.label} · {item.meta.unit}</option>)}
        </select>
      </label>}
      {loadingReport && <p role="status">Preparing local and upstream statistics…</p>}
      {report && <article aria-label="Location basin report">
        <h3>{report.name}</h3><p>{report.meta.label} · {report.meta.source_release}</p>
        <div className="poi-downloads">{['PDF', 'ZIP', 'CSV', 'JSON'].map(kind => <button key={kind} disabled={!!busy}
          onClick={() => download(kind)}>{kind === 'ZIP' ? 'Report & data (ZIP)' : `Download ${kind}`}</button>)}</div>
        {busy && <p role="status">Preparing {busy} download…</p>}
        <ReportMap key={`${active}-${variable}`} report={report}/>
        <div className="poi-summaries"><Summary report={report} scope="local"/><Summary report={report} scope="upstream"/></div>
        {report.morphology?.traced_area_km2 < report.morphology?.reported_upstream_area_km2 * 0.95 &&
          <p role="note">The traced network covers less than 95% of the reported upstream area. Results describe the published network only.</p>}
        {!!report.geometry_missing_ids.length && <p role="note">{report.geometry_missing_ids.length} upstream basins have statistics but no display boundary.</p>}
        {variable === 'snw_pc_s' && <p>Snow-cover records are not suitable for trend analysis.</p>}
        <details><summary>Monthly local and upstream statistics</summary><div className="poi-table"><table>
          <thead><tr><th>Month</th><th>Local mean</th><th>Local coverage</th><th>Upstream mean</th><th>Upstream coverage</th></tr></thead>
          <tbody>{report.local.rows.map((row, i) => <tr key={i}><th>{row.year}-{String(row.month).padStart(2, '0')}</th>
            <td>{formatNumber(row.mean_observed_area, 2)}</td><td>{formatNumber(row.area_coverage_percent, 1)}%</td>
            <td>{formatNumber(report.upstream.rows[i].mean_observed_area, 2)}</td><td>{formatNumber(report.upstream.rows[i].area_coverage_percent, 1)}%</td></tr>)}</tbody>
        </table></div></details>
        {report.morphology && <details><summary>Upstream catchment morphology</summary><dl className="poi-morphology">
          {MORPHOLOGY_FIELDS.map(([key, label, unit]) => <div key={key}><dt>{label}</dt><dd>{formatNumber(report.morphology[key], 2)} {unit}</dd></div>)}
        </dl></details>}
        <AttributeDetails key={active} report={report}/>
        <details><summary>Methods &amp; sources</summary><p>{REPORT_METHOD}</p><p>{report.upstream.total.note}</p>
          <p>Means describe the area with observations; the CSV/JSON also include full-area means, totals, coverage and extrema. Missing values are not replaced with zero.</p>
          {report.morphology_notes.map(note => <p key={note}>{note}</p>)}
          <p>Generated {report.generatedAt}. The ZIP contains the full report and relevant geometry, attribute and monthly files for this location and variable.</p>
        </details>
      </article>}
    </div>
  </div>;
}
