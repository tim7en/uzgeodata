import assert from 'node:assert/strict';
import test from 'node:test';
import {
  classArea, classShare, distribution, dominantClass, selectedTimeline, shareChange, totalArea,
} from '../INTERFACE/landcoverModel.js';

const record = {
  years: {
    2020: { 1: 20, 5: 30, 8: 50 },
    2021: { 1: 10, 5: 50, 8: 40 },
  },
};

test('land-cover area and share use the complete annual composition', () => {
  assert.equal(totalArea(record, 2020), 100);
  assert.equal(classArea(record, 2020, 5), 30);
  assert.equal(classShare(record, 2020, 5), 30);
});

test('change is expressed as percentage-point share change', () => {
  assert.equal(shareChange(record, 2021, 5, [2020, 2021]), 20);
  assert.equal(shareChange(record, 2020, 5, [2020, 2021]), null);
});

test('dominant class returns the class code with most area', () => {
  assert.equal(dominantClass(record, 2020), 8);
  assert.equal(dominantClass(record, 2021), 5);
});

test('timeline preserves unavailable years as null', () => {
  assert.deepEqual(selectedTimeline(record, [2019, 2020, 2021], 1), [
    { year: 2019, area: null, share: null },
    { year: 2020, area: 20, share: 20 },
    { year: 2021, area: 10, share: 10 },
  ]);
});

test('change distributions are symmetric around zero', () => {
  const result = distribution([record], 2021, 5, 'change', [2020, 2021], 4);
  assert.equal(result.bins[0].from, -20);
  assert.equal(result.bins.at(-1).to, 20);
  assert.equal(result.values.length, 1);
});
