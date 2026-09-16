import React from 'react';
import ReactDOM from 'react-dom/client';
import ErrorBoundary from './ErrorBoundary.jsx';
import { initTheme } from './ThemeToggle.jsx';
import CaseStudies from './CaseStudies.jsx';
import 'leaflet/dist/leaflet.css';
import './case-studies.css';
import { initLang, mountSelect } from './lang.js';
import { autoHideHeader } from './chrome.js';

initTheme();
initLang();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><ErrorBoundary><CaseStudies /></ErrorBoundary></React.StrictMode>
);
requestAnimationFrame(() => {
  autoHideHeader(document.querySelector('.cs-header'));
  const nav = document.querySelector('.cs-header nav');
  if (nav) {
    const host = document.createElement('span');
    host.style.display = 'inline-flex';
    nav.appendChild(host);
    mountSelect(host);
  }
});
