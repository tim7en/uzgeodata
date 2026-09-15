import React from 'react';
import ReactDOM from 'react-dom/client';
import MetadataCatalogue from './MetadataCatalogue.jsx';
import ErrorBoundary from './ErrorBoundary.jsx';
import './metadata.css';
import { initTheme } from './ThemeToggle.jsx';
initTheme();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><ErrorBoundary><MetadataCatalogue /></ErrorBoundary></React.StrictMode>
);
