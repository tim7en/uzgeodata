import React from 'react';
import { GLOSSARY, term } from './glossary.js';

// A glossary term in the reader's language, shielded from machine translation; the
// English original is kept as the title so a reader can always see what it stands for.
export default function Term({ id, children }) {
  const english = GLOSSARY[id]?.en || children;
  const text = term(id, children);
  return <span translate="no" className="notranslate" title={text !== english ? english : undefined}>{text}</span>;
}
