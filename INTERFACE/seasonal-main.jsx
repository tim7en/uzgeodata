import React from 'react';
import ReactDOM from 'react-dom/client';
import 'leaflet/dist/leaflet.css';
import './landing.css';
import './seasonalForecast.css';
import SeasonalPage from './SeasonalPage.jsx';
import { initTheme } from './ThemeToggle.jsx';
initTheme();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><SeasonalPage/></React.StrictMode>,
);
