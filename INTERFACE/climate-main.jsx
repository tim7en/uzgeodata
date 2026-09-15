import React from 'react';
import ReactDOM from 'react-dom/client';
import 'leaflet/dist/leaflet.css';
import ClimateObservatory from './ClimateObservatory.jsx';
import './climate.css';
import { initTheme } from './ThemeToggle.jsx';
initTheme();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><ClimateObservatory/></React.StrictMode>,
);
