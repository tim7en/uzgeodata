import React from 'react';
import ReactDOM from 'react-dom/client';
import HydrographyExplorer from './HydrographyExplorer';
import 'leaflet/dist/leaflet.css';
import './hydrography.css';
import { initTheme } from './ThemeToggle.jsx';
initTheme();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><HydrographyExplorer /></React.StrictMode>
);
