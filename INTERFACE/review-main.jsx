import React from 'react';
import { createRoot } from 'react-dom/client';
import LayerReview from './LayerReview.jsx';
import 'leaflet/dist/leaflet.css';
import './review.css';

createRoot(document.getElementById('root')).render(<LayerReview/>);
