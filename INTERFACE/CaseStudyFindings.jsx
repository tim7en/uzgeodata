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
    fetch(HIGHLIGHTS_URL)
      .then(response => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then(document => active && setHighlights(document))
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  if (!highlights) return null;
  const { study, findings, reports, counts } = highlights;

  return <section className="cs-findings cs-panel" id="findings">
    <div className="cs-findings-head">
      <div>
        <span className="cs-eyebrow">01 / WHAT THE STUDY FOUND</span>
        <h2>{study.question}</h2>
        <p>
          {counts.findings} findings drawn from {counts.figures} figures and {counts.reports} reports.
          Each number is read from the published evidence rather than restated, and the results that
          did not work are here too.
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
        {finding.figure && <a className="cs-finding-figure" href={finding.figure} target="_blank" rel="noreferrer">
          <img src={finding.figure} alt={finding.headline} loading="lazy"/>
          <span>Open figure <ArrowUpRight size={11}/></span>
        </a>}
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
