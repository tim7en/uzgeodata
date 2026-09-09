import React, { useEffect, useState } from 'react';
import CaseStudyFindings from './CaseStudyFindings.jsx';
import AdvancedCaseStudy, { Readiness } from './AdvancedCaseStudy';
import CaseStudyMap from './CaseStudyMap';
import SabitovCaseStudy from './SabitovCaseStudy';
import { Download, Droplets, ArrowRight } from 'lucide-react';

const BASE = '/data/case-studies/';
const fetchJSON = async url => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not load case-study evidence (${response.status}).`);
  return response.json();
};

import Chart from './features/case-studies/TimeSeriesChart.jsx';
import { StationEvidence, DischargeEvidence } from './features/case-studies/ObservationEvidence.jsx';
import StudyPortfolio from './features/case-studies/StudyPortfolio.jsx';
import RegionalStationStudy from './features/case-studies/RegionalStationStudy.jsx';

export default function CaseStudies() {
  const [data, setData] = useState(null), [geometry, setGeometry] = useState(null), [error, setError] = useState('');
  const [advanced, setAdvanced] = useState(null), [environment, setEnvironment] = useState(null);
  const [study, setStudy] = useState(() => window.location.hash === '#regional-study' ? 'regional' : 'chirchik');
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
    <header className="cs-header"><a className="cs-logo" href="/"><Droplets size={22} /> UZGEODATA <span>/ FIELD STUDIES</span></a><nav><a href="/climate.html">Climate</a><a href="/hydrography.html">Hydrography</a><a href={`${BASE}chirchik-deep-study.md`} download><Download size={14} /> Study report</a></nav></header>
    <main>
      <nav className="cs-study-switch" aria-label="Case study"><button aria-pressed={study === 'chirchik'} onClick={() => { setStudy('chirchik'); history.replaceState(null, '', '#chirchik-study'); }}>Chirchik / Pskem · basin processes</button><button aria-pressed={study === 'regional'} onClick={() => { setStudy('regional'); history.replaceState(null, '', '#regional-study'); }}>Regional network · station–satellite relationships</button></nav>
      {study === 'regional' ? <RegionalStationStudy/> : <>
      <section id="chirchik-study" className="cs-hero"><div><span className="cs-eyebrow">CHIRCHIK–CHARVAK / WESTERN TIAN SHAN</span><h1>Mountain processes.<br /><em>Measured evidence.</em></h1><p>A historical Pskem-centred experiment within the Chirchik basin: connect station observations, satellite snow and vegetation, terrain and modelled water balance. Extension to the whole Chirchik requires independent tributary checks.</p>
        <div className="cs-hero-actions"><a className="cs-primary" href="#portfolio">Explore the case studies <ArrowRight size={16} /></a><a href="#station-evidence">Inspect the observations ↓</a></div></div>
        <aside className="cs-scope"><span className="cs-eyebrow">THE STARTING POINT</span><h2>Pskem first.</h2><p>{data.scope}</p><div><strong>{s.joint_months}</strong><span>joint climate–flow months<br />{s.joint_start} to {s.joint_end}</span></div><p className="cs-note">Historical validation, satellite checks and three modelling approaches are available. Operational readiness remains limited by gauge location and the age of discharge observations.</p></aside>
      </section>
      <div className="cs-top-stats"><div><strong>{stations.length}</strong><span>Meteorological stations in this experiment</span></div><div><strong>2001–2017</strong><span>Historical Pskem discharge</span></div><div><strong>2010–2024</strong><span>Pskem climate record</span></div><div><strong>{data.studies.length}</strong><span>Documented study protocols</span></div></div>
      <section className="cs-panel"><h2>One methodology, distinct evidence layers</h2><div className="cs-table-wrap"><table><thead><tr><th>Layer</th><th>Scientific role</th><th>Boundary of the claim</th></tr></thead><tbody>
        <tr><td>Stations and gauges</td><td>Temperature, precipitation and screened discharge targets</td><td>Coordinate, calendar, missingness and unit checks precede comparisons.</td></tr>
        <tr><td>Elevation, snow and glaciers</td><td>Height-stratified temperature and melt hypotheses; satellite snow timing</td><td>Snow-covered area is not measured snowpack water equivalent. Glacier catalogue centres are not outlines.</td></tr>
        <tr><td>Land cover, vegetation and soil</td><td>Surface context and evapotranspiration constraints</td><td>Classification changes require verification; soil temperature does not define soil type.</td></tr>
        <tr><td>Climate forcing and water balance</td><td>Compare gridded precipitation/air temperature with observations; test runoff pathways</td><td>Reanalysis and satellite-derived estimates remain distinct from instrument measurements.</td></tr>
        <tr><td>Evaluation</td><td>Seasonal benchmarks, held-out years, anomaly relationships and process checks</td><td>Discharge-stratified splits and retrospective forcing do not establish real-time forecast skill.</td></tr>
      </tbody></table></div><p className="cs-note">Keep negative results and uncertainty alongside successful experiments. A calibrated Pskem model does not yet validate Chatkal, Ugam, the entire Chirchik, or downstream allocation.</p></section>
      <CaseStudyFindings/>
      <nav className="cs-jump-nav" aria-label="Study sections"><a href="#findings">Findings</a><a href="#station-evidence">Station validation</a><a href="#snow-evidence">Snow</a><a href="#elevation-evidence">Elevation & land cover</a><a href="#modelling-evidence">Model comparison</a><a href="#sabitov-methods">Sabitov methodology</a><a href="#portfolio">Research protocols</a></nav>
      <Readiness environment={environment}/><CaseStudyMap data={data} geometry={geometry} environment={environment}/>
      <StationEvidence data={data} /><DischargeEvidence data={data} /><AdvancedCaseStudy advanced={advanced} environment={environment} Chart={Chart}/><SabitovCaseStudy Chart={Chart}/>
      <details className="cs-panel" id="portfolio"><summary>Research protocols and evidence thresholds</summary><StudyPortfolio data={data} /></details>
      <section className="cs-downloads cs-panel"><div><span className="cs-eyebrow">04 / REPRODUCIBLE EVIDENCE</span><h2>Take the analysis with you.</h2><p>Existing station URIs, basin identifiers, source hashes and processing rules travel with the results.</p></div><div>{[['chirchik-report.md', 'Full case-study report'], ['pskem-observation-evidence.pdf', 'Observation figure · vector PDF'], ['pskem-observation-evidence.png', 'Observation figure · PNG'], ['chirchik.json', 'All results & protocols · JSON'], ['chirchik.manifest.json', 'Source hashes & QC policy'], ['discharge-audit.csv', 'Discharge quality audit · CSV'], ['station-annual.csv', 'Complete-year climate summaries · CSV'], ['joint-climate-discharge.csv', 'Matched climate–flow months · CSV']].map(([file, label]) => <a key={file} href={BASE + file} download>{label}<Download size={15} /></a>)}</div></section>
      </>}
    </main><footer>UZGEODATA / HYDROCLIMATE CASE STUDIES <span>Historical evidence · Provenance and dates accompany each study</span></footer>
  </div>;
}
