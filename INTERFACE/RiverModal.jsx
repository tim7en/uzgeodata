import React, { useEffect, useState } from 'react';
import { X, Download } from 'lucide-react';
import ObservationChart from './ObservationChart.jsx';
import './damModal.css';
import './case-studies.css';

function riverToCsv(data) {
  const lines = ['date,wse_m,wse_outlier,width_m,partial_pass'];
  for (const o of data.observations) lines.push([o.time, o.wse_m ?? '', o.wse_outlier, o.width_m ?? '', o.partial].join(','));
  return lines.join('\n') + '\n';
}

function downloadText(text, type, filename) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = filename;
  document.body.appendChild(link); link.click(); link.remove();
  requestAnimationFrame(() => URL.revokeObjectURL(url));
}

/** Reach records are fetched lazily, one small file per reach, the same
 * shape as the lake/reservoir SWOT records -- only clicked reaches need to
 * load their observations. */
function useReachRecord(reachId) {
  const [state, setState] = useState({ status: 'loading', data: null });
  useEffect(() => {
    let live = true;
    setState({ status: 'loading', data: null });
    fetch(`/data/case-studies/rivers/swot/${reachId}.json`, { cache: 'no-store' })
      .then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(data => { if (live) setState({ status: 'ready', data }); })
      .catch(() => { if (live) setState({ status: 'error', data: null }); });
    return () => { live = false; };
  }, [reachId]);
  return state;
}

export default function RiverModal({ reach, onClose }) {
  useEffect(() => {
    const close = e => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [onClose]);

  const { status, data } = useReachRecord(reach.reach_id);

  return <div className="dam-modal lake-modal" role="dialog" aria-modal="true"
    aria-label={`SWOT river reach on the ${reach.river_group}`} onClick={onClose}>
    <div className="dam-modal-card" onClick={e => e.stopPropagation()}>
      <button className="dam-modal-close" aria-label="Close" onClick={onClose}><X size={15}/></button>
      <header>
        <span className="dam-modal-kicker">River reach · {reach.basin}</span>
        <h2>{reach.river_group}</h2>
        <p className="dam-modal-sub">SWORD reach {reach.reach_id}. Prior database width{' '}
          {reach.p_width_m ? `${Math.round(reach.p_width_m)} m` : 'not recorded'}, length{' '}
          {reach.p_length_m ? `${(reach.p_length_m / 1000).toFixed(1)} km` : 'not recorded'}.</p>
      </header>

      {status === 'loading' && <p>Loading SWOT record…</p>}
      {status === 'error' && <p>This reach has no usable SWOT record yet.</p>}
      {status === 'ready' && data && (() => {
        const obs = data.observations;
        const first = obs[0], last = obs[obs.length - 1];
        const nPartial = obs.filter(o => o.partial).length;
        const hasWidth = obs.some(o => o.width_m != null);
        return <>
          <section className="dam-modal-block">
            <h3>Satellite monitoring (SWOT)</h3>
            <p>NASA/CNES's SWOT mission has observed this reach of the {data.river_group} by radar, roughly
              every 21 days, from {first.time} to {last.time} ({obs.length} quality-passing overpasses,
              {' '}{nPartial} imaging only part of the channel cross-section). Points are raw per-pass
              readings, not a monthly average; the line is a LOESS trend through them.</p>
            <ObservationChart observations={obs} loess={data.wse_loess} valueKey="wse_m" flagKey="wse_outlier"
              flagLabel="Outlier reading" unit="m" title="Water surface elevation" color="#edb06c" />
            {hasWidth && <ObservationChart observations={obs} loess={data.width_loess} valueKey="width_m" flagKey="partial"
              flagLabel="Partial pass" unit="m" title="Channel width" color="#58c9e5" />}
            <div className="station-modal-downloads">
              <button onClick={() => downloadText(riverToCsv(data), 'text/csv;charset=utf-8', `swot-reach-${reach.reach_id}.csv`)}><Download size={13}/> CSV</button>
              <button onClick={() => downloadText(JSON.stringify(data, null, 2), 'application/json', `swot-reach-${reach.reach_id}.json`)}><Download size={13}/> JSON</button>
            </div>
          </section>
        </>;
      })()}
      <section className="dam-modal-block">
        <h3>Source</h3>
        <p>NASA/CNES SWOT mission, SWOT_L2_HR_RiverSP_2.0 via PO.DAAC Hydrocron, reach geometry and prior
          attributes from the SWOT River Database (SWORD) via CNES/Theia Hydroweb. Quality-filtered:
          bad-quality passes (reach_q 3) dropped; a statistically implausible elevation reading is flagged,
          not hidden.</p>
      </section>
    </div>
  </div>;
}
