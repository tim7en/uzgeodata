import React, { useState } from 'react';
import { ArrowUpRight, Download, ArrowRight } from 'lucide-react';
const BASE = '/data/case-studies/';
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmt = (x, digits = 1) => x == null ? '—' : Number(x).toLocaleString('en', { maximumFractionDigits: digits });
export default function StudyPortfolio({ data }) {
  const [selected, setSelected] = useState(data.studies[0].id);
  const study = data.studies.find(r => r.id === selected);
  return <section className="cs-portfolio">
    <div className="cs-section-head"><div><span className="cs-eyebrow">03 / THE RESEARCH PROGRAMME</span><h2>{data.studies.length} connected study protocols.</h2></div><p>Each starts with a testable question<br />and ends with an evidence threshold.</p></div>
    <div className="cs-study-layout"><nav className="cs-study-nav" aria-label="Choose a case study">{data.studies.map((r, i) => <button key={r.id} aria-pressed={selected === r.id} onClick={() => setSelected(r.id)}>
      <span>0{i + 1}</span><div><strong>{r.theme}</strong><small>{r.status}</small></div><ArrowRight size={16} /></button>)}</nav>
      <article className="cs-study"><span className="cs-status">{study.status}</span><h3>{study.title}</h3><p className="cs-question">{study.question}</p>
        <div className="cs-hypothesis"><span className="cs-eyebrow">HYPOTHESIS</span><p>{study.hypothesis}</p></div>
        <h4>Observation base</h4><p>{study.observations}</p>
        <h4>Study protocol</h4><ol>{study.method.map(step => <li key={step}>{step}</li>)}</ol>
        <div className="cs-study-columns"><div><h4>Evaluation</h4><ul>{study.metrics.map(v => <li key={v}>{v}</li>)}</ul></div><div><h4>Deliverables</h4><ul>{study.deliverables.map(v => <li key={v}>{v}</li>)}</ul></div></div>
        <div className="cs-gates"><h4>Evidence needed before stronger claims</h4>{study.gates.map(v => <p key={v}>{v}</p>)}</div>
        <h4>Decision supported</h4><p>{study.decision}</p>
        <div className="cs-sources">{data.sources.filter(r => study.sources.includes(r.id)).map(r => <a key={r.id} href={r.url}>{r.title} <ArrowUpRight size={12} /></a>)}</div>
      </article></div>
  </section>;
}
