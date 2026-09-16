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
const LANG_PENDING_KEY = 'uzgeodata-lang-pending';
const TRANSLATION_TIMEOUT = 20000;

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

export function languageLabel(lang) {
  return LANGS.find(([id]) => id === lang)?.[1] || lang;
}

export function translationProgressCopy(lang) {
  return lang === PAGE_LANGUAGE
    ? { title: 'Restoring original', detail: 'Loading the authoritative English page…' }
    : { title: 'Switching language', detail: `Translating this page to ${languageLabel(lang)}…` };
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

/** A saved explicit choice must beat a stale cookie left by Google's widget. */
export function resolveActiveLang(stored, cookie) {
  if (stored && isSupported(stored)) return stored;
  return cookie && isSupported(cookie) ? cookie : 'en';
}

/** The language currently applied to the page. */
export function activeLang() {
  return resolveActiveLang(storedLang(), cookieLang());
}

function clearGoogtrans() {
  const expired = 'expires=Thu, 01 Jan 1970 00:00:00 GMT';
  document.cookie = `googtrans=;path=/;${expired}`;

  // Translate Element may promote its cookie to the current domain. Clear
  // every valid parent candidate as well as the host-only cookie above.
  const hostname = document.location?.hostname || '';
  if (!hostname || hostname === 'localhost' || hostname.includes(':') || /^\d+(\.\d+){3}$/.test(hostname)) return;
  const labels = hostname.split('.');
  for (let index = 0; index < labels.length - 1; index += 1) {
    document.cookie = `googtrans=;path=/;domain=.${labels.slice(index).join('.')};${expired}`;
  }
}

function setGoogtrans(lang) {
  clearGoogtrans();
  if (lang === 'en') {
    return;
  } else {
    document.cookie = `googtrans=/en/${lang};path=/;SameSite=Lax`;
  }
}

/** Explicit choice: persist and reload so every script (and Google) starts in that language. */
export function setLang(lang) {
  if (!isSupported(lang)) return;
  showTranslationProgress(lang);
  try { sessionStorage.setItem(LANG_PENDING_KEY, lang); } catch { /* progress can still show before reload */ }
  try { localStorage.setItem(LANG_KEY, lang); } catch { /* storage blocked; cookie still applies */ }
  setGoogtrans(lang);
  // Give the browser one paint so the reader sees immediate feedback before
  // the reload carries the indicator into the newly selected language.
  requestAnimationFrame(() => window.setTimeout(() => window.location.reload(), 80));
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
    updateTranslationProgress('Applying translated text…');
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

function pendingLang() {
  try {
    const value = sessionStorage.getItem(LANG_PENDING_KEY);
    return value && isSupported(value) ? value : null;
  } catch {
    return null;
  }
}

function clearPendingLang() {
  try { sessionStorage.removeItem(LANG_PENDING_KEY); } catch { /* storage blocked */ }
}

function showTranslationProgress(lang) {
  injectStyle();
  const copy = translationProgressCopy(lang);
  let progress = document.getElementById('uz-translation-progress');
  if (!progress) {
    progress = document.createElement('div');
    progress.id = 'uz-translation-progress';
    progress.className = 'uz-translation-progress notranslate';
    progress.setAttribute('translate', 'no');
    progress.setAttribute('role', 'status');
    progress.setAttribute('aria-live', 'polite');
    progress.setAttribute('aria-atomic', 'true');
    progress.innerHTML = '<i aria-hidden="true"></i><span><strong></strong><small></small></span>';
    (document.body || document.documentElement).appendChild(progress);
  }
  progress.dataset.lang = lang;
  progress.classList.remove('is-complete');
  progress.querySelector('strong').textContent = copy.title;
  progress.querySelector('small').textContent = copy.detail;
  return progress;
}

function updateTranslationProgress(detail) {
  const progress = document.getElementById('uz-translation-progress');
  if (progress) progress.querySelector('small').textContent = detail;
}

function finishTranslationProgress() {
  clearPendingLang();
  const progress = document.getElementById('uz-translation-progress');
  if (!progress) return;
  const lang = progress.dataset.lang || PAGE_LANGUAGE;
  progress.classList.add('is-complete');
  progress.querySelector('strong').textContent = lang === PAGE_LANGUAGE ? 'English restored' : `${languageLabel(lang)} ready`;
  progress.querySelector('small').textContent = 'The page is ready.';
  window.setTimeout(() => progress.remove(), 650);
}

function finishWhenPageLoads() {
  const finish = () => requestAnimationFrame(() => requestAnimationFrame(finishTranslationProgress));
  if (document.readyState === 'complete') finish();
  else window.addEventListener('load', finish, { once: true });
}

function watchTranslationReady() {
  const translated = () => document.documentElement.classList.contains('translated-ltr')
    || document.documentElement.classList.contains('translated-rtl')
    || document.body?.classList.contains('translated-ltr')
    || document.body?.classList.contains('translated-rtl');
  if (translated()) {
    finishTranslationProgress();
    return;
  }
  const observer = new MutationObserver(() => {
    if (!translated()) return;
    observer.disconnect();
    window.clearTimeout(timeout);
    finishTranslationProgress();
  });
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'], subtree: true });
  const timeout = window.setTimeout(() => {
    observer.disconnect();
    ensureTranslationError();
  }, TRANSLATION_TIMEOUT);
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
  clearPendingLang();
  document.getElementById('uz-translation-progress')?.remove();
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
.uz-translation-progress{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:3200;display:flex;align-items:center;gap:11px;min-width:250px;max-width:calc(100vw - 28px);padding:10px 14px;color:#e8eef0;background:rgba(4,9,12,.96);border:1px solid #2a3a41;border-radius:7px;box-shadow:0 10px 32px rgba(0,0,0,.28);font-family:var(--body,system-ui,sans-serif)}
.uz-translation-progress>i{width:17px;height:17px;flex:none;border:2px solid rgba(255,255,255,.24);border-top-color:#4cc9f0;border-radius:50%;animation:uz-lang-spin .8s linear infinite}
.uz-translation-progress>span{display:flex;flex-direction:column;gap:2px;min-width:0}
.uz-translation-progress strong{font-size:11px;line-height:1.2;letter-spacing:.06em;text-transform:uppercase}
.uz-translation-progress small{font-size:11px;line-height:1.35;color:#aebcc3}
.uz-translation-progress.is-complete>i{border:0;animation:none;display:grid;place-items:center;color:#8fe3b0}
.uz-translation-progress.is-complete>i::after{content:'✓';font-size:17px;font-style:normal;font-weight:700}
[data-theme="light"] .uz-translation-progress{color:#141c1f;background:rgba(251,252,252,.98);border-color:#c5d0d5;box-shadow:0 10px 30px rgba(15,30,38,.16)}
[data-theme="light"] .uz-translation-progress>i{border-color:rgba(0,0,0,.18);border-top-color:#0c6f8d}
[data-theme="light"] .uz-translation-progress small{color:#515f64}
@keyframes uz-lang-spin{to{transform:rotate(360deg)}}
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
  const pending = pendingLang();
  document.documentElement.lang = lang;
  setGoogtrans(lang);
  if (lang === 'en') {
    if (pending === 'en') {
      showTranslationProgress(lang);
      finishWhenPageLoads();
    } else {
      clearPendingLang();
    }
    return;
  }
  showTranslationProgress(lang);
  document.documentElement.dataset.mt = lang;
  watchTranslationReady();
  loadTranslateElement();
  watchNotranslate();
}
