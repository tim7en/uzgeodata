import React, { useEffect, useState } from 'react';
import { ArrowUpRight, FileText } from 'lucide-react';

const HIGHLIGHTS_URL = '/data/case-studies/case-study-highlights.json';

const KIND_LABELS = {
  validated: 'Validated',
  negative: 'Negative result',
  limitation: 'Limitation',
};

/**
 * What the study found, at the top of the study.
 *
 * Every value is read from `case-study-highlights.json`, which the pipeline
 * derives from the published evidence — so a rerun that changes the evidence
 * changes this section, and a finding that stops being true cannot survive here
 * as prose. Negative and limiting results are shown beside the positive ones:
 * a summary of only what worked would misrepresent the work.
 */
export default function CaseStudyFindings() {
  const [highlights, setHighlights] = useState(null);

  useEffect(() => {
    let active = true;
    fetch(HIGHLIGHTS_URL, {cache:'no-cache'})
      .then(response => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then(document => active && setHighlights(document))
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  if (!highlights) return null;
  const { reports } = highlights;
  const supporting = new Set(['product-station-agreement','snow-sensor-agreement','charvak-water-surface','monthly-discharge-trend','discharge-record-verified']);
  const findings = highlights.findings.filter(f => supporting.has(f.id));

  return <section className="cs-findings cs-panel" id="findings">
    <div className="cs-findings-head">
      <div>
        <span className="cs-eyebrow">SUPPORTING ANALYSES / HISTORICAL CONTEXT</span>
        <h2>Product agreement, water extent and observation checks</h2>
        <p>
          These {findings.length} analyses answer separate questions. Satellite agreement and reservoir extent
          are not evidence of runoff forecast accuracy. Original reports retain their own methods and dates.
        </p>
      </div>
      <dl className="cs-findings-tally">
        {Object.entries(
          findings.reduce((tally, finding) => ({ ...tally, [finding.kind]: (tally[finding.kind] || 0) + 1 }), {}),
        ).map(([kind, count]) => <div key={kind} className={`cs-tally-${kind}`}>
          <dt>{KIND_LABELS[kind] || kind}</dt>
          <dd>{count}</dd>
        </div>)}
      </dl>
    </div>

    <div className="cs-findings-grid">
      {findings.map(finding => <article key={finding.id} className={`cs-finding cs-finding-${finding.kind}`}>
        <header>
          <span>{KIND_LABELS[finding.kind] || finding.kind}</span>
          <b>{finding.value}<em>{finding.valueLabel}</em></b>
        </header>
        <h3>{finding.headline}</h3>
        <p>{finding.detail}</p>
        {(finding.figures || (finding.figure ? [finding.figure] : [])).map((figure, index) =>
          <a className="cs-finding-figure" key={figure} href={figure} target="_blank" rel="noreferrer">
            <img src={`${figure}?v=${encodeURIComponent(highlights.generatedAt || highlights.generated_at || '')}`} alt={`${finding.headline} (${index + 1})`} loading="lazy"/>
            <span>Open figure <ArrowUpRight size={11}/></span>
          </a>)}
        <footer>Evidence: <code>{finding.evidence.split('/').pop()}</code></footer>
      </article>)}
    </div>

    <div className="cs-findings-reports">
      <span className="cs-eyebrow">READ IT IN FULL</span>
      <div>{reports.map(report => <a key={report.href} href={report.href} target="_blank" rel="noreferrer">
        <FileText size={14}/>
        <span>{report.label}</span>
      </a>)}</div>
    </div>
  </section>;
}
