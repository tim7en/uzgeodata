import React from 'react';
initTheme();
import { createRoot } from 'react-dom/client';
import LayerReview from './LayerReview.jsx';
import 'leaflet/dist/leaflet.css';
import './review.css';
import { initTheme } from './ThemeToggle.jsx';

createRoot(document.getElementById('root')).render(<LayerReview/>);
