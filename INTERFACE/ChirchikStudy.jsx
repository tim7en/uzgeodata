import React, { useEffect, useState } from 'react';
import CaseStudyFindings from './CaseStudyFindings.jsx';
import AdvancedCaseStudy, { Readiness } from './AdvancedCaseStudy';
import CaseStudyMap from './CaseStudyMap';
import SabitovCaseStudy from './SabitovCaseStudy';
import { Download, Droplets, ArrowRight } from 'lucide-react';
import ThemeToggle from './ThemeToggle.jsx';

const BASE = '/data/case-studies/';
const fetchJSON = async url => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not load case-study evidence (${response.status}).`);
  return response.json();
};

import Chart from './features/case-studies/TimeSeriesChart.jsx';
import { StationEvidence, DischargeEvidence } from './features/case-studies/ObservationEvidence.jsx';
import StudyPortfolio from './features/case-studies/StudyPortfolio.jsx';
import CurrentModel from './features/case-studies/CurrentModel.jsx';
import ModelReview from './features/case-studies/ModelReview.jsx';
import ReproducibilityPackage from './features/case-studies/ReproducibilityPackage.jsx';

export default function ChirchikStudy() {
  const [data, setData] = useState(null), [geometry, setGeometry] = useState(null), [error, setError] = useState('');
  const [advanced, setAdvanced] = useState(null), [environment, setEnvironment] = useState(null);
  useEffect(() => {
    const reveal = () => {
      const target = document.getElementById(window.location.hash.slice(1));
      if (!target) return;
      let parent = target.parentElement;
      while (parent) { if (parent.tagName === 'DETAILS') parent.open = true; parent = parent.parentElement; }
      if (window.location.hash !== '#chirchik-study') target.scrollIntoView();
    };
    if (data) reveal();
    window.addEventListener('hashchange',reveal);
    return () => window.removeEventListener('hashchange',reveal);
  }, [data]);
  useEffect(() => {
    let active = true;
    Promise.all([fetchJSON(`${BASE}chirchik.json`), fetchJSON(`${BASE}pskem-candidate-catchment.geojson`), fetchJSON(`${BASE}advanced-validation.json`), fetchJSON(`${BASE}environment-modelling.json`)])
      .then(([d, g, a, e]) => { if (active) { setData(d); setGeometry(g); setAdvanced(a); setEnvironment(e); } })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);
  if (error) return <main className="cs-loading" role="alert"><h1>Case-study evidence could not be loaded.</h1><p>{error}</p><a href="/">Return to UzGeoData</a></main>;
  if (!data) return <main className="cs-loading" role="status">Loading the Chirchik evidence record…</main>;
  const { summary: s } = data;
  const stations = [...new Map(data.inventory.map(r => [r.station_id, r])).values()];
  return <div className="cs-app">
    <header className="cs-header"><a className="cs-logo" href="/"><Droplets size={22} /> UZGEODATA <span>/ FIELD STUDIES</span></a><nav><a href="/climate.html">Climate</a><a href="/hydrography.html">Hydrography</a><a href={`${BASE}chirchik-deep-study.md`} download><Download size={14} /> Study report</a><ThemeToggle/></nav></header>
    <main>
      <nav className="cs-study-switch" aria-label="Case studies"><a href="/case-studies.html">← All case studies</a><a href="#regional-study">Regional station study →</a></nav>
      <section id="chirchik-study" className="cs-hero"><div><span className="cs-eyebrow">CHIRCHIK–CHARVAK / WESTERN TIAN SHAN</span><h1>Mountain processes.<br /><em>Measured evidence.</em></h1><p>A historical Pskem-centred experiment within the Chirchik basin: connect station observations, satellite snow and vegetation, terrain and modelled water balance. Extension to the whole Chirchik requires independent tributary checks.</p>
        <div className="cs-hero-actions"><a className="cs-primary" href="#model-review">Review the new model test <ArrowRight size={16} /></a><a href="#reproducibility">Data, method and tests ↓</a></div></div>
        <aside className="cs-scope"><span className="cs-eyebrow">THE STARTING POINT</span><h2>Pskem first.</h2><p>{data.scope}</p><div><strong>{s.joint_months}</strong><span>joint climate–flow months<br />{s.joint_start} to {s.joint_end}</span></div><p className="cs-note">A new chronological test is presented first. The earlier stratified fit is preserved as a reference, not a directly comparable accuracy claim. Operational readiness remains limited by gauge location and the historical discharge record.</p></aside>
      </section>
      <div className="cs-top-stats"><div><strong>{stations.length}</strong><span>Meteorological stations in this experiment</span></div><div><strong>2001–2017</strong><span>Historical Pskem discharge</span></div><div><strong>2010–2024</strong><span>Pskem climate record</span></div><div><strong>{data.studies.length}</strong><span>Documented study protocols</span></div></div>
      <ModelReview/>
      <ReproducibilityPackage/>
      <details className="cs-panel" id="reference-model"><summary>Earlier published reference model — different validation split</summary><CurrentModel/></details>
      <section className="cs-panel"><h2>One methodology, distinct evidence layers</h2><div className="cs-table-wrap"><table><thead><tr><th>Layer</th><th>Scientific role</th><th>Boundary of the claim</th></tr></thead><tbody>
        <tr><td>Stations and gauges</td><td>Temperature, precipitation and screened discharge targets</td><td>Coordinate, calendar, missingness and unit checks precede comparisons.</td></tr>
        <tr><td>Elevation, snow and glaciers</td><td>Height-stratified temperature and melt hypotheses; satellite snow timing</td><td>Snow-covered area is not measured snowpack water equivalent. Glacier catalogue centres are not outlines.</td></tr>
        <tr><td>Land cover, vegetation and soil</td><td>Surface context and evapotranspiration constraints</td><td>Classification changes require verification; soil temperature does not define soil type.</td></tr>
        <tr><td>Climate forcing and water balance</td><td>Compare gridded precipitation/air temperature with observations; test runoff pathways</td><td>Reanalysis and satellite-derived estimates remain distinct from instrument measurements.</td></tr>
        <tr><td>Evaluation</td><td>Seasonal benchmarks, held-out years, anomaly relationships and process checks</td><td>Discharge-stratified splits and retrospective forcing do not establish real-time forecast skill.</td></tr>
      </tbody></table></div><p className="cs-note">Keep negative results and uncertainty alongside successful experiments. A calibrated Pskem model does not yet validate Chatkal, Ugam, the entire Chirchik, or downstream allocation.</p></section>
      <details className="cs-panel" id="supporting-evidence"><summary>Supporting satellite and observation studies — separate from runoff validation</summary><CaseStudyFindings/></details>
      <nav className="cs-jump-nav" aria-label="Study sections"><a href="#model-review">New model evaluation</a><a href="#reproducibility">Reproducibility package</a><a href="#station-evidence">Station validation</a><a href="#snow-evidence">Snow</a><a href="#elevation-evidence">Elevation & land cover</a><a href="#modelling-evidence">Earlier models</a><a href="#sabitov-methods">Sabitov methodology</a><a href="#portfolio">Research protocols</a></nav>
      <Readiness environment={environment}/><CaseStudyMap data={data} geometry={geometry} environment={environment}/>
      <StationEvidence data={data} /><DischargeEvidence data={data} />
      <details className="cs-panel" id="earlier-models"><summary>Earlier model experiments and detailed process checks</summary><p>These experiments have different inputs and evaluation protocols. Compare scores only after matching temporal support and validation splits.</p><AdvancedCaseStudy advanced={advanced} environment={environment} Chart={Chart}/><SabitovCaseStudy Chart={Chart}/></details>
      <details className="cs-panel" id="portfolio"><summary>Research protocols and evidence thresholds</summary><StudyPortfolio data={data} /></details>
      <section className="cs-downloads cs-panel"><div><span className="cs-eyebrow">04 / REPRODUCIBLE EVIDENCE</span><h2>Take the analysis with you.</h2><p>The package above lists every input hash, every command and every test. These files carry the same record for offline use.</p></div><div>{[['reproducibility-package.json', 'Reproducibility package · data, method, tests'], ['reproduction-check.json', 'Rebuild comparison · JSON'], ['chirchik-report.md', 'Full case-study report'], ['pskem-observation-evidence.pdf', 'Observation figure · vector PDF'], ['pskem-observation-evidence.png', 'Observation figure · PNG'], ['chirchik.json', 'All results & protocols · JSON'], ['chirchik.manifest.json', 'Source hashes & QC policy'], ['discharge-audit.csv', 'Discharge quality audit · CSV'], ['station-annual.csv', 'Complete-year climate summaries · CSV'], ['joint-climate-discharge.csv', 'Matched climate–flow months · CSV']].map(([file, label]) => <a key={file} href={BASE + file} download>{label}<Download size={15} /></a>)}</div></section>
    </main><footer>UZGEODATA / HYDROCLIMATE CASE STUDIES <span>Historical evidence · Provenance and dates accompany each study</span></footer>
  </div>;
}
