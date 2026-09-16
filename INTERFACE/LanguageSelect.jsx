import React, { useEffect, useRef } from 'react';
import { mountSelect } from './lang.js';

/** Mount the shared DOM-based selector only after its React host exists. */
export default function LanguageSelect({ className, style }) {
  const hostRef = useRef(null);
  useEffect(() => {
    if (hostRef.current && !hostRef.current.firstChild) mountSelect(hostRef.current);
  }, []);
  return <span ref={hostRef} className={className} style={style}/>;
}
