import React from 'react';
import ReactDOM from 'react-dom/client';
import ErrorBoundary from './ErrorBoundary.jsx';
import { initTheme } from './ThemeToggle.jsx';
import CaseStudies from './CaseStudies.jsx';
import 'leaflet/dist/leaflet.css';
import './case-studies.css';

initTheme();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><ErrorBoundary><CaseStudies /></ErrorBoundary></React.StrictMode>
);
