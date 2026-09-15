import React from 'react';
initTheme();
import {createRoot} from 'react-dom/client';
import OntologyUniverse from './OntologyUniverse.jsx';
import './ontology.css';
import './ontology-enhancements.css';
import { initTheme } from './ThemeToggle.jsx';

createRoot(document.getElementById('root')).render(<OntologyUniverse/>);
