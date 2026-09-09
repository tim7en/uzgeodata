import React, { lazy, Suspense, useEffect, useState } from 'react';
import StudyDirectory from './features/case-studies/StudyDirectory.jsx';
const ChirchikStudy = lazy(() => import('./ChirchikStudy.jsx'));
const RegionalStudy = lazy(() => import('./features/case-studies/RegionalStationStudy.jsx'));

export default function CaseStudies() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const change = () => setHash(window.location.hash);
    window.addEventListener('hashchange', change);
    return () => window.removeEventListener('hashchange', change);
  }, []);
  useEffect(() => {
    document.title = !hash ? 'Case Studies — UzGeoData' : hash === '#regional-study'
      ? 'Regional Station Study — UzGeoData' : 'Chirchik / Pskem Study — UzGeoData';
    if (!hash || ['#regional-study','#chirchik-study'].includes(hash)) window.scrollTo(0,0);
  }, [hash]);
  if (!hash) return <StudyDirectory/>;
  return <Suspense fallback={<main className="cs-loading" role="status">Loading the selected study…</main>}>
    {hash === '#regional-study' ? <div className="cs-app"><header className="cs-header"><a className="cs-logo" href="/">UZGEODATA</a><nav><a href="/case-studies.html">All case studies</a><a href="#chirchik-study">Chirchik / Pskem</a></nav></header><main><RegionalStudy/></main></div> : <ChirchikStudy/>}
  </Suspense>;
}
