import React from 'react';
import { ArrowUpRight, Droplets } from 'lucide-react';
import usePublishedData from './usePublishedData.js';

export default function StudyDirectory() {
  const {data,error,retry} = usePublishedData('/data/case-studies/study-directory.json');
  return <div className="cs-app cs-directory">
    <a className="cs-skip" href="#study-cards">Skip to case studies</a>
    <header className="cs-header"><a className="cs-logo" href="/"><Droplets size={22}/> UZGEODATA</a><nav><a href="/">Explore the basin map <ArrowUpRight size={14}/></a><ThemeToggle/></nav></header>
    <main>
      <section className="cs-directory-hero"><span className="cs-eyebrow">HYDROCLIMATE / EVIDENCE IN PRACTICE</span><h1>Understand the water.<br/><em>Explore the evidence.</em></h1><p>From snow in the mountains to conditions around a weather station. Choose a study to explore its question, observations and results.</p></section>
      <section id="study-cards" aria-label="Available case studies">
        {error ? <div className="cs-panel" role="alert"><h2>Study summaries are unavailable.</h2><p>{error}</p><button className="cs-primary" onClick={retry}>Try again</button></div> : !data ? <p role="status">Loading the latest study summaries…</p> : <>
          <div className="cs-directory-grid">{data.studies.map(study => <a className="cs-study-card" href={study.href} key={study.id}>
            <div className="cs-card-image"><img src={`${study.image}?v=${study.image_revision}`} width="1080" height="552" alt={study.image_alt}/><span>{study.region}</span></div>
            <div className="cs-card-copy"><span className="cs-card-status">{study.status}</span><h2>{study.title}</h2><p>{study.aim}</p>
              <div className="cs-card-evidence"><strong>{study.metric.toLocaleString('en',{maximumFractionDigits:3})}</strong><span>{study.metric_label}<small>{study.detail}</small></span></div>
              <div className="cs-card-cta"><span>Explore this study</span><ArrowUpRight size={22}/></div>
            </div>
          </a>)}</div>
          <p className="cs-directory-note">Study-specific evidence, not interchangeable accuracy scores. Model results describe historical validation; regional correlations are exploratory. Summaries rebuilt {data.generated_at.slice(0,10)}.</p>
        </>}
      </section>
      <section className="cs-directory-promise"><h2>Clear questions. Traceable answers.</h2><p>Every study keeps measured observations separate from satellite estimates and models. Inside, find interactive charts, data coverage, limitations and downloadable evidence.</p></section>
    </main><footer>UZGEODATA / CASE STUDIES <span>Observed · Modelled · Evaluated</span></footer>
  </div>;
}
