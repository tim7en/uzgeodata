import test from 'node:test';
import assert from 'node:assert/strict';
import { GLOSSARY, GLOSSARY_REVIEW, term } from '../INTERFACE/glossary.js';
import { BASIS } from '../INTERFACE/assessmentModel.js';

test('every glossary term has English, Russian and Uzbek', () => {
  for (const [id, entry] of Object.entries(GLOSSARY)) {
    for (const lang of ['en', 'ru', 'uz']) assert.ok(entry[lang], `${id} lacks ${lang}`);
  }
});

test('the snow forecast is named as a river-flow forecast, not weather', () => {
  assert.match(term('tab_snow', '', 'ru'), /стока/);
  assert.doesNotMatch(term('tab_snow', '', 'ru'), /погод/);
  assert.match(term('tab_snow', '', 'uz'), /oqim/);
});

test('every evidence label the assessment uses is in the glossary', () => {
  for (const key of Object.keys(BASIS)) assert.equal(GLOSSARY[`basis_${key}`].en, BASIS[key]);
});

test('unknown languages and terms fall back to English, then to the given text', () => {
  assert.equal(term('tab_history', '', 'de'), 'Monthly record');
  assert.equal(term('no_such_term', 'as given', 'ru'), 'as given');
});

test('the glossary says it has not been reviewed until someone has', () => {
  assert.ok(GLOSSARY_REVIEW.status === 'draft' || GLOSSARY_REVIEW.reviewed_by);
});
