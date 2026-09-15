import React from 'react';
import ReactDOM from 'react-dom/client';
import RelationshipTables from './RelationshipTables';
import './relationships.css';
import { initTheme } from './ThemeToggle.jsx';
initTheme();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><RelationshipTables /></React.StrictMode>
);
