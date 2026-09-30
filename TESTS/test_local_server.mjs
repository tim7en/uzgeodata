import test from 'node:test';
import assert from 'node:assert/strict';
import { onLocalServer } from '../INTERFACE/localServer.js';

test('the operator APIs are only asked for on the local server', () => {
  assert.equal(onLocalServer({ hostname: 'localhost' }), true);
  assert.equal(onLocalServer({ hostname: '127.0.0.1' }), true);
  assert.equal(onLocalServer({ hostname: 'uzgeodata.uz' }), false);
  assert.equal(onLocalServer(undefined), false);
});
