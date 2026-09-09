import React, { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import StudyDirectory from './features/case-studies/StudyDirectory.jsx';
const ChirchikStudy = lazy(() => import('./ChirchikStudy.jsx'));
const RegionalStudy = lazy(() => import('./features/case-studies/RegionalStationStudy.jsx'));

// A study is addressable two ways: by its own path, so it can be cited, linked
// and copied out of the address bar, and by the fragment the directory has
// always used. Both resolve to the same view, so old links keep working.
const PATHS = { '/case-studies/chirchik': 'chirchik', '/case-studies/regional': 'regional' };
const HASHES = { '#regional-study': 'regional' };
const TITLES = {
  chirchik: 'Chirchik / Pskem Study — UzGeoData',
  regional: 'Regional Station Study — UzGeoData',
};

function selection(pathname, hash) {
  if (PATHS[pathname]) return PATHS[pathname];
  if (!hash) return null;
  return HASHES[hash] || 'chirchik';
}

export default function CaseStudies() {
  const [route, setRoute] = useState(() => ({
    pathname: window.location.pathname,
    hash: window.location.hash,
  }));
  const sync = useCallback(() => setRoute({
    pathname: window.location.pathname,
    hash: window.location.hash,
  }), []);

  useEffect(() => {
    window.addEventListener('hashchange', sync);
    // pushState does not fire an event of its own, so back and forward are the
    // only navigations left to listen for once the click handler below syncs.
    window.addEventListener('popstate', sync);
    return () => {
      window.removeEventListener('hashchange', sync);
      window.removeEventListener('popstate', sync);
    };
  }, [sync]);

  // A card carries the citable path in its href, so copying the link gives a
  // real address; the click is taken over here to avoid a full reload.
  useEffect(() => {
    const navigate = event => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey
          || event.shiftKey || event.altKey) return;
      const anchor = event.target.closest('a[href]');
      if (!anchor || anchor.target === '_blank' || anchor.hasAttribute('download')) return;
      const url = new URL(anchor.href, window.location.origin);
      if (url.origin !== window.location.origin || !PATHS[url.pathname]) return;
      event.preventDefault();
      window.history.pushState(null, '', url.pathname);
      sync();
    };
    document.addEventListener('click', navigate);
    return () => document.removeEventListener('click', navigate);
  }, [sync]);

  const study = selection(route.pathname, route.hash);
  useEffect(() => {
    document.title = TITLES[study] || 'Case Studies — UzGeoData';
    if (!route.hash || ['#regional-study', '#chirchik-study'].includes(route.hash)) window.scrollTo(0, 0);
  }, [study, route.hash]);

  if (!study) return <StudyDirectory/>;
  return <Suspense fallback={<main className="cs-loading" role="status">Loading the selected study…</main>}>
    {study === 'regional'
      ? <div className="cs-app">
        <header className="cs-header">
          <a className="cs-logo" href="/">UZGEODATA</a>
          <nav><a href="/case-studies.html">All case studies</a><a href="/case-studies/chirchik">Chirchik / Pskem</a></nav>
        </header>
        <main><RegionalStudy/></main>
      </div>
      : <ChirchikStudy/>}
  </Suspense>;
}
