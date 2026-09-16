/* Entry point for the static information pages: language aid plus the
   auto-hiding header. Loaded as a module script from each page, so Vite
   bundles it with the rest of the build. */
import { initLang, mountSelect, activeLang } from './lang.js';
import { autoHideHeader } from './chrome.js';

initLang();

const header = document.querySelector('.site-header');
if (header) {
  autoHideHeader(header);
  const nav = header.querySelector('nav');
  const explorerButton = nav && nav.querySelector('.button');
  if (nav) {
    const host = document.createElement('span');
    if (explorerButton) nav.insertBefore(host, explorerButton);
    else nav.appendChild(host);
    mountSelect(host, activeLang());
  }
}
