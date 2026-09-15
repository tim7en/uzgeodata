import React from 'react';
import ReactDOM from 'react-dom/client';
import 'leaflet/dist/leaflet.css';
import LandcoverExplorer from './LandcoverExplorer.jsx';
import './landcover.css';
import { initTheme } from './ThemeToggle.jsx';
initTheme();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><LandcoverExplorer/></React.StrictMode>,
);
