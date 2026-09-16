/* Language aid for the whole site.
 *
 * English is the authoritative language of the scientific record. On top of it
 * a reader can request a machine-assisted rendering: the PC default language
 * is detected automatically on first visit, an explicit choice from the
 * switcher overrides it, and the choice persists in the browser. Translation
 * is done by Google's translate element against the published English DOM, so
 * the registry, tests and code stay single-source.
 *
 * Two things must never be silently translated: identifiers (HYBAS ids,
 * variable codes) and the disclaimer that this is machine translation. The
 * observer below marks code and pre elements notranslate, and the note names
 * the English original as authoritative.
 */
export const LANG_KEY = 'uzgeodata-lang';
export const PAGE_LANGUAGE = 'en';
export const TRANSLATE_ELEMENT_URL = 'https://translate.google.com/translate_a/element.js?cb=uzGTInit';

// Curated for the audience: English plus the Central Asian languages and a
// few widely used ones. The list is what the switcher offers.
export const LANGS = [
  ['en', 'English'],
  ['ru', 'Русский'],
  ['uz', 'Oʻzbekcha'],
  ['kk', 'Қазақша'],
  ['tg', 'Тоҷикӣ'],
  ['tk', 'Türkmençe'],
  ['az', 'Azərbaycanca'],
  ['zh-CN', '简体中文'],
  ['de', 'Deutsch'],
  ['fr', 'Français'],
  ['es', 'Español'],
];

// Machine-translation notices in the target language, English fallback.
const MT_NOTES = {
  ru: 'Машинный перевод Google. Авторитетная версия — английский оригинал.',
  uz: 'Google tarjimasi. Muallif matni — inglizcha asl nusxa.',
  kk: 'Google аудармасы. Авторытылған нұсқа — ағылшын түпнұсқасы.',
  tg: 'Тарҷумаи Google. Матни аслӣ забони англисӣ аст.',
  tk: 'Google terjimesi. Avtoritet versýa — iňlisçe asyl.',
  az: 'Google tərcüməsi. Orijinal mətn ingilis dilindədir.',
};

export function isSupported(lang) {
  return LANGS.some(([id]) => id === lang);
}

export function normalizeBrowserLang(browserLang) {
  const value = String(browserLang || '').toLowerCase();
  if (!value) return 'en';
  if (value.startsWith('zh')) return 'zh-CN';
  return value.slice(0, 2);
}

/** Pure resolution: explicit stored choice wins, then the PC default, then English. */
export function resolveLang(browserLang, stored) {
  if (stored === 'en') return 'en';
  if (stored && isSupported(stored)) return stored;
  const browser = normalizeBrowserLang(browserLang);
  if (browser === 'en') return 'en';
  return isSupported(browser) ? browser : 'en';
}

export function storedLang() {
  try {
    const value = localStorage.getItem(LANG_KEY);
    return value && isSupported(value) ? value : null;
  } catch {
    return null; // Private windows and blocked storage are normal, not errors.
  }
}

export function cookieLang() {
  const match = /(?:^|;\s*)googtrans=\/en\/([a-z-]+)/i.exec(document.cookie || '');
  return match ? match[1] : null;
}

/** The language currently applied to the page, cookie first (set by Google or us). */
export function activeLang() {
  return cookieLang() || storedLang() || 'en';
}

function setGoogtrans(lang) {
  if (lang === 'en') {
    document.cookie = 'googtrans=;path=/;max-age=0';
  } else {
    document.cookie = `googtrans=/en/${lang};path=/`;
  }
}

/** Explicit choice: persist and reload so every script (and Google) starts in that language. */
export function setLang(lang) {
  if (!isSupported(lang)) return;
  try { localStorage.setItem(LANG_KEY, lang); } catch { /* storage blocked; cookie still applies */ }
  setGoogtrans(lang);
  window.location.reload();
}

/** Apply a language without the switcher: the PC default on first visit. */
export function applyLang(lang) {
  setGoogtrans(lang);
  try { localStorage.setItem(LANG_KEY, lang); } catch { /* ignore */ }
}

export function loadTranslateElement() {
  if (document.getElementById('uz-gt-script')) return;
  window.uzGTInit = () => {
    if (!window.google?.translate) {
      ensureTranslationError();
      return;
    }
    const host = document.getElementById('uz-gt-host');
    if (!host) return;
    new window.google.translate.TranslateElement(
      { pageLanguage: PAGE_LANGUAGE, autoDisplay: false, layout: window.google.translate.TranslateElement.InlineLayout.SIMPLE },
      'uz-gt-host',
    );
    ensureMtNote(activeLang());
    markNotranslate();
  };
  const host = document.createElement('div');
  host.id = 'uz-gt-host';
  host.style.cssText = 'position:absolute;left:-9999px;top:-9999px;height:1px;overflow:hidden';
  document.body.appendChild(host);
  const script = document.createElement('script');
  script.id = 'uz-gt-script';
  script.src = TRANSLATE_ELEMENT_URL;
  script.async = true;
  script.addEventListener('error', ensureTranslationError, { once: true });
  document.body.appendChild(script);
}

const NOTRANSLATE = 'code, pre, kbd, samp';

function markNotranslate() {
  // Identifiers and code must survive translation: a HYBAS id or a variable
  // code that Google rewrites is a corrupted citation.
  document.querySelectorAll(NOTRANSLATE).forEach(el => {
    el.classList.add('notranslate');
    el.setAttribute('translate', 'no');
  });
}

function watchNotranslate() {
  if (!document.body) return;
  const observer = new MutationObserver(() => markNotranslate());
  observer.observe(document.body, { childList: true, subtree: true });
}

export function ensureMtNote(lang) {
  if (sessionStorage.getItem('uz-mt-hide')) return;
  if (document.getElementById('uz-mt-note')) return;
  const note = document.createElement('div');
  note.id = 'uz-mt-note';
  note.className = 'uz-mt-note notranslate';
  note.setAttribute('translate', 'no');
  note.innerHTML = '';
  const text = document.createElement('span');
  text.textContent = MT_NOTES[lang] || 'Machine translation via Google. The English original is authoritative.';
  const dismiss = document.createElement('button');
  dismiss.type = 'button';
  dismiss.setAttribute('aria-label', 'Hide translation notice');
  dismiss.textContent = '×';
  dismiss.addEventListener('click', () => {
    sessionStorage.setItem('uz-mt-hide', '1');
    note.remove();
  });
  note.append(text, dismiss);
  (document.body || document.documentElement).appendChild(note);
}

function ensureTranslationError() {
  if (document.getElementById('uz-mt-error')) return;
  const note = document.createElement('div');
  note.id = 'uz-mt-error';
  note.className = 'uz-mt-note notranslate';
  note.setAttribute('translate', 'no');
  const text = document.createElement('span');
  text.textContent = 'Translation could not load. Check your connection or content blocker, then reload the page.';
  const dismiss = document.createElement('button');
  dismiss.type = 'button';
  dismiss.setAttribute('aria-label', 'Hide translation error');
  dismiss.textContent = '×';
  dismiss.addEventListener('click', () => note.remove());
  note.append(text, dismiss);
  (document.body || document.documentElement).appendChild(note);
}

let styleInjected = false;
function injectStyle() {
  if (styleInjected) return;
  styleInjected = true;
  const style = document.createElement('style');
  style.textContent = `
.uz-lang-wrap{display:inline-flex;align-items:center;gap:5px}
.uz-lang-select{font:inherit;font-size:12px;color:inherit;background:transparent;border:1px solid var(--line,#d0dadf);border-radius:4px;padding:4px 6px;cursor:pointer;max-width:140px}
.uz-lang-select option{color:#141c1f;background:#ffffff}
.uz-mt-note{position:fixed;left:10px;bottom:10px;z-index:2200;display:flex;gap:8px;align-items:center;max-width:360px;font-size:10.5px;line-height:1.45;color:#e8eef0;background:rgba(4,9,12,.92);border:1px solid #2a3a41;border-radius:6px;padding:8px 10px}
[data-theme="light"] .uz-mt-note{color:#141c1f;background:rgba(251,252,252,.96);border-color:#d0dadf}
.uz-mt-note button{border:0;background:none;color:inherit;cursor:pointer;font:inherit;line-height:1;padding:0 2px}
`;
  document.head.appendChild(style);
}

export function mountSelect(container, current = activeLang()) {
  injectStyle();
  const wrap = document.createElement('span');
  wrap.className = 'uz-lang-wrap';
  const select = document.createElement('select');
  select.className = 'uz-lang-select';
  select.setAttribute('aria-label', 'Language / Язык');
  for (const [id, name] of LANGS) {
    const option = document.createElement('option');
    option.value = id;
    option.textContent = name;
    if (id === current) option.selected = true;
    select.appendChild(option);
  }
  select.addEventListener('change', () => setLang(select.value));
  wrap.appendChild(select);
  container.appendChild(wrap);
  return wrap;
}

/** Entry point for every page: detect, apply, and enable translation when non-English. */
export function initLang() {
  injectStyle();
  const lang = resolveLang(navigator.language, storedLang());
  document.documentElement.lang = lang;
  setGoogtrans(lang);
  if (lang === 'en') return;
  document.documentElement.dataset.mt = lang;
  loadTranslateElement();
  watchNotranslate();
}
