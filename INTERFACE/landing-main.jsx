import React from 'react';
import ReactDOM from 'react-dom/client';
import LandingMap from './LandingMap.jsx';
import ErrorBoundary from './ErrorBoundary.jsx';
import { initTheme } from './ThemeToggle.jsx';
import { initLang } from './lang.js';
import 'leaflet/dist/leaflet.css';
import './landing.css';

initTheme();
initLang();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><ErrorBoundary><LandingMap /></ErrorBoundary></React.StrictMode>
);
