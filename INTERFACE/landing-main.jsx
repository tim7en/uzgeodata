import React from 'react';
import ReactDOM from 'react-dom/client';
import LandingMap from './LandingMap.jsx';
import 'leaflet/dist/leaflet.css';
import './landing.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><LandingMap /></React.StrictMode>
);
