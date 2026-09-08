import React from 'react';
import ReactDOM from 'react-dom/client';
import AtlasExplorer from './AtlasExplorer.jsx';
import ErrorBoundary from './ErrorBoundary.jsx';
import 'leaflet/dist/leaflet.css';
import './atlas.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><ErrorBoundary><AtlasExplorer /></ErrorBoundary></React.StrictMode>
);
