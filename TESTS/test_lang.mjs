import assert from 'node:assert/strict';
import test from 'node:test';
import {
  LANGS, TRANSLATE_ELEMENT_URL, isSupported, languageLabel, normalizeBrowserLang,
  resolveActiveLang, resolveLang, translationProgressCopy,
} from '../INTERFACE/lang.js';

test('the language list is unique, English-first, and covers the regional audience', () => {
  const ids = LANGS.map(([id]) => id);
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(ids[0], 'en');
  for (const needed of ['ru', 'uz', 'kk', 'tg', 'tk']) assert.ok(ids.includes(needed));
});

test('a stored explicit choice wins over the browser default', () => {
  assert.equal(resolveLang('ru-RU', 'de'), 'de');
  assert.equal(resolveLang('ru-RU', 'en'), 'en');
});

test('the PC default is honoured when nothing is stored', () => {
  assert.equal(resolveLang('ru-RU', null), 'ru');
  assert.equal(resolveLang('uz-UZ', null), 'uz');
  assert.equal(resolveLang('zh-CN,cn', null), 'zh-CN');
  assert.equal(resolveLang('fr', null), 'fr');
  assert.equal(resolveLang('en-GB,en', null), 'en');
});

test('unsupported browsers fall back to English rather than guessing', () => {
  assert.equal(resolveLang('xx-YY', null), 'en');
  assert.equal(resolveLang('', null), 'en');
  assert.equal(resolveLang(undefined, 'qq'), 'en');
});

test('browser tags are normalized to the registry ids', () => {
  assert.equal(normalizeBrowserLang('zh-TW'), 'zh-CN');
  assert.equal(normalizeBrowserLang('RU-ru'), 'ru');
  assert.equal(normalizeBrowserLang(''), 'en');
});

test('isSupported agrees with the registry', () => {
  for (const [id] of LANGS) assert.ok(isSupported(id));
  assert.equal(isSupported('qq'), false);
});

test('an explicit saved language overrides stale Google translation cookies', () => {
  assert.equal(resolveActiveLang('en', 'ru'), 'en');
  assert.equal(resolveActiveLang('uz', 'ru'), 'uz');
  assert.equal(resolveActiveLang(null, 'ru'), 'ru');
  assert.equal(resolveActiveLang(null, 'qq'), 'en');
});

test('translation progress distinguishes translated pages from restored English', () => {
  assert.deepEqual(translationProgressCopy('en'), {
    title: 'Restoring original', detail: 'Loading the authoritative English page…',
  });
  assert.deepEqual(translationProgressCopy('ru'), {
    title: 'Switching language', detail: 'Translating this page to Русский…',
  });
  assert.equal(languageLabel('uz'), 'Oʻzbekcha');
});

test('translation loads from the active Google Translate Element endpoint', () => {
  const url = new URL(TRANSLATE_ELEMENT_URL);
  assert.equal(url.hostname, 'translate.google.com');
  assert.equal(url.pathname, '/translate_a/element.js');
  assert.equal(url.searchParams.get('cb'), 'uzGTInit');
});
