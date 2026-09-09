import React, { useCallback, useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';

const KEY = 'uzgeodata-theme';

/** What the operating system asks for, when the reader has not chosen. */
function preferred() {
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function stored() {
  try {
    const saved = localStorage.getItem(KEY);
    return saved === 'light' || saved === 'dark' ? saved : null;
  } catch {
    return null; // Private windows and blocked storage are normal, not errors.
  }
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
}

/**
 * The theme as it currently stands on the document.
 *
 * The map needs it too: a basemap tuned for a dark page is unreadable on a
 * light one. Reading the attribute rather than a shared context keeps the
 * toggle usable from any page without threading a provider through it.
 */
export function useTheme() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || 'dark');
  useEffect(() => {
    const observer = new MutationObserver(
      () => setTheme(document.documentElement.dataset.theme || 'dark'));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => observer.disconnect();
  }, []);
  return theme;
}

/**
 * Read the theme before React mounts, so the first paint is already correct.
 * Called from each page entry; without it a light reader sees a dark flash.
 */
export function initTheme() {
  applyTheme(stored() || preferred());
}

/**
 * A two-state switch: dark or light, remembered per browser.
 *
 * The system preference is the default rather than a hardcoded dark, because a
 * reader who has asked their machine for light pages has already answered this
 * question. An explicit choice wins over the system and survives a reload; when
 * no choice has been made, a change in the system preference is followed live.
 */
export default function ThemeToggle({ className = '' }) {
  const [theme, setTheme] = useState(() => stored() || preferred());
  const [explicit, setExplicit] = useState(() => stored() !== null);

  useEffect(() => { applyTheme(theme); }, [theme]);

  useEffect(() => {
    if (explicit) return undefined;
    const query = window.matchMedia?.('(prefers-color-scheme: light)');
    if (!query) return undefined;
    const follow = event => setTheme(event.matches ? 'light' : 'dark');
    query.addEventListener('change', follow);
    return () => query.removeEventListener('change', follow);
  }, [explicit]);

  const toggle = useCallback(() => {
    setTheme(current => {
      const next = current === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(KEY, next); } catch { /* nothing to remember it with */ }
      return next;
    });
    setExplicit(true);
  }, []);

  const next = theme === 'dark' ? 'light' : 'dark';
  return <button type="button" className={`theme-toggle ${className}`.trim()} onClick={toggle}
    aria-pressed={theme === 'light'} title={`Switch to ${next} mode`}
    aria-label={`Switch to ${next} mode`}>
    {theme === 'dark' ? <Sun size={15}/> : <Moon size={15}/>}
    <span>{next === 'light' ? 'Light' : 'Dark'}</span>
  </button>;
}
