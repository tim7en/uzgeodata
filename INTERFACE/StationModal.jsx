import React, { useEffect, useState } from 'react';
import { Download, X } from 'lucide-react';
import { formatNumber } from './landingModel.js';
import { downloadName, recordSummary, toCsv } from './stationModel.js';
import './damModal.css';

const PLACEMENT_LABEL = {
  coordinate_supplied_by_source: 'Coordinate from the source',
  consistent_with_network: 'Name match, not contradicted',
  departs_from_network_relationship: 'Name match, departs from the check',
  not_checked: 'Name match, not checked',
};

/**
 * One station. The figures are secondary here: what a reader most needs is whether
 * this point is where the observations were actually recorded, so placement leads and
 * is stated in full rather than reduced to a badge.
 */
export default function StationModal({ station, onClose }) {
  const [record, setRecord] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const close = event => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [onClose]);

  // The record is fetched when the station is opened rather than with the map: three
  // hundred of these is eighteen megabytes, and a reader opens one.
  useEffect(() => {
    if (!station.data_key) return undefined;
    let live = true;
    setRecord(null);
    setFailed(false);
    fetch(`/data/hydromet/stations/${station.data_key}.json`, { cache: 'no-store' })
      .then(response => { if (!response.ok) throw Error(String(response.status)); return response.json(); })
      .then(data => { if (live) setRecord(data); })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [station.data_key]);

  const save = (text, type, extension) => {
    const blob = new Blob([text], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = downloadName(record, extension);
    document.body.appendChild(link);
    link.click();
    link.remove();
    // Revoked on the next frame: Safari has not finished reading it when click returns.
    requestAnimationFrame(() => URL.revokeObjectURL(url));
  };

  const summary = recordSummary(record);

  const value = v => v === '' || v == null ? '—' : formatNumber(Number(v));
  const span = station.first_year && station.last_year
    ? `${station.first_year}–${station.last_year}` : 'not recorded';
  const suspect = station.placement_status === 'departs_from_network_relationship';

  return <div className="dam-modal station-modal" role="dialog" aria-modal="true"
    aria-label={`Meteorological station ${station.name}`} onClick={onClose}>
    <div className="dam-modal-card" onClick={event => event.stopPropagation()}>
      <button className="dam-modal-close" aria-label="Close" onClick={onClose}><X size={15}/></button>

      <header>
        <span className="dam-modal-kicker">
          {station.archive_label} · {station.country || 'country not recorded'}
          {station.province ? ` · ${station.province}` : ''}
        </span>
        <h2>{station.name}</h2>
        <p className="dam-modal-sub">
          {station.measures.length ? `Records ${station.measures.join(', ')}.` : 'No measures recorded.'}
          {' '}{formatNumber(station.observations)} monthly values, {span}.
        </p>
      </header>

      <dl className="dam-modal-figures">
        <div><dt>Elevation</dt><dd>{value(station.elevation_m)} <em>m</em></dd></div>
        <div><dt>Monthly values</dt><dd>{value(station.observations)}</dd></div>
        <div><dt>Record</dt><dd>{span}</dd></div>
        {station.recorded_air_c ? <div><dt>Mean air temperature</dt>
          <dd>{value(station.recorded_air_c)} <em>°C</em></dd></div> : null}
        {station.reanalysis_air_c ? <div><dt>Reanalysis at this point</dt>
          <dd>{value(station.reanalysis_air_c)} <em>°C</em></dd></div> : null}
        {station.wmo_code ? <div><dt>WMO code</dt><dd>{station.wmo_code}</dd></div> : null}
      </dl>

      <section className={`dam-modal-block${suspect ? ' station-modal-warn' : ''}`}>
        <h3>Where this point comes from — {PLACEMENT_LABEL[station.placement_status] || 'unknown'}</h3>
        <p>{station.placement}</p>
        {station.placement_status === 'consistent_with_network' ? <p>
          This station&rsquo;s recorded temperature sits where the network&rsquo;s
          elevation relationship says a station at this coordinate should. That leaves the
          match uncontradicted; it does not establish that these observations were recorded here.
        </p> : null}
        {suspect ? <p>
          This station departs from the relationship the rest of the network follows, by
          {' '}{value(station.residual_c)} °C. That can mean a wrong coordinate, and it can equally
          mean a deep valley or a sheltered site. It is a reason to look, not a finding.
        </p> : null}
        {station.placement_status === 'coordinate_supplied_by_source' ? <p>
          No name matching was involved, so the placement carries whatever accuracy the
          original survey had and nothing was inferred on top of it.
        </p> : null}
      </section>

      <section className="dam-modal-block">
        <h3>Take this station&rsquo;s record</h3>
        {!station.data_key ? <p>
          No observations survive for this station: every value in the delivery was the
          archive&rsquo;s missing-data marker, so there is nothing to download.
        </p> : failed ? <p role="alert">
          This station&rsquo;s record could not be loaded. The layer is still available in full below.
        </p> : !record ? <p role="status">Loading this station&rsquo;s record&hellip;</p> : <>
          <p>
            {formatNumber(summary.rows)} monthly values, {summary.firstYear}&ndash;{summary.lastYear}
            {summary.missing ? `, of which ${formatNumber(summary.missing)} are recorded as missing` : ''}.
            Both files carry the same rows and the same notes on placement and treatment, so the
            numbers cannot differ between them.
          </p>
          <div className="station-modal-downloads">
            <button type="button" onClick={() => save(toCsv(record), 'text/csv;charset=utf-8', 'csv')}>
              <Download size={13}/> CSV
            </button>
            <button type="button"
              onClick={() => save(JSON.stringify(record, null, 2), 'application/json', 'json')}>
              <Download size={13}/> JSON
            </button>
          </div>
        </>}
        <p>Station identifier <code>{station.station_id}</code>.</p>
        {/* The gauge caveat belongs only to stations that actually gauge rainfall;
            on a soil-temperature site it would be noise dressed as a warning. */}
        {station.measures.includes('precipitation') ? <p>
          {station.archive === 'nsidc'
            ? 'Precipitation here is corrected for gauge type and wetting but not for wind, so'
              + ' winter totals at exposed sites remain understated.'
            : 'Precipitation here carries no gauge correction, so totals understate true'
              + ' precipitation, most of all for snow at windy sites.'}
        </p> : null}
        {station.archive === 'nsidc' ? <p>This archive ends in 2003.</p> : null}
        <a href="/data/hydroclimate/meteo-stations.geojson" download>Download the station layer ↗</a>
      </section>
    </div>
  </div>;
}
