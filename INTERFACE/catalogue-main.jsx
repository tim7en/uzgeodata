import React from 'react';
initTheme();
import { createRoot } from 'react-dom/client';
import DataCatalogue from './DataCatalogue.jsx';
import './catalogue.css';
import { initTheme } from './ThemeToggle.jsx';

createRoot(document.getElementById('root')).render(<DataCatalogue/>);
