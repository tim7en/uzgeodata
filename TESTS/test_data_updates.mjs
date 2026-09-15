import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { DataUpdates } from '../SERVER/dataUpdates.mjs';

async function fixture(t, options = {}) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'uz-updates-'));
  const service = new DataUpdates({ root, directory: path.join(root, 'state'),
    groups: [{ id: 'rain', label: 'Rain', requires: [] }, { id: 'snow', label: 'Snow', requires: [] }], ...options });
  await service.init({ timer: false });
  t.after(async () => { await service.close(); await fs.rm(root, { recursive: true, force: true }); });
  return service;
}
async function settled(service) {
  for (let i = 0; i < 200 && (service.busy || service.state.jobs.some(j => j.status === 'queued')); i++) await new Promise(resolve => setTimeout(resolve, 5));
  assert.equal(service.busy, false, 'worker completed');
  await service.saving;
}

test('unknown commands and missing prerequisites are rejected before starting a job', async t => {
  let calls = 0;
  const service = await fixture(t, { run: async () => { calls++; } });
  await assert.rejects(service.enqueue('rain; touch /tmp/injection'), /Unknown/);
  service.groups[0].requires = ['absent-data'];
  await assert.rejects(service.enqueue('rain'), /Required local inputs/);
  assert.equal(calls, 0);
  assert.equal(service.state.jobs.length, 0);
});
test('simultaneous clicks deduplicate and groups run serially', async t => {
  const started = []; let unblock;
  const service = await fixture(t, { run: async group => { started.push(group.id); if (group.id === 'rain') await new Promise(resolve => { unblock = resolve; }); } });
  const [a, b] = await Promise.all([service.enqueue('rain'), service.enqueue('rain')]);
  assert.equal(a.id, b.id);
  await service.enqueue('snow');
  for (let i = 0; i < 100 && !unblock; i++) await new Promise(resolve => setTimeout(resolve, 5));
  assert.deepEqual(started, ['rain']);
  unblock(); await settled(service);
  assert.deepEqual(started, ['rain', 'snow']);
  assert.ok(service.state.jobs.every(job => job.status === 'succeeded' && job.progress === 100));
});
test('failures retain their message and never report 100 percent success', async t => {
  const service = await fixture(t, { run: async (_group, progress) => { progress({ progress: 42, message: 'Acquiring' }); throw Error('Provider unavailable'); } });
  await service.enqueue('rain'); await settled(service);
  const [job] = service.state.jobs;
  assert.equal(job.status, 'failed'); assert.equal(job.progress, 42); assert.equal(job.message, 'Provider unavailable');
});
test('schedules persist, run once when overdue, and can be switched off', async t => {
  let time = Date.parse('2026-09-14T00:00:00Z'), calls = 0;
  const service = await fixture(t, { now: () => time, run: async () => { calls++; } });
  await assert.rejects(service.schedule('rain', 0.5), /Choose off/);
  await service.schedule('rain', 1);
  assert.equal(JSON.parse(await fs.readFile(service.file)).schedules.rain.days, 1);
  time += 86400001; await Promise.all([service.tick(), service.tick()]); await settled(service);
  assert.equal(calls, 1);
  await service.tick(); assert.equal(calls, 1);
  await service.schedule('rain', 0); time += 3 * 86400000; await service.tick(); assert.equal(calls, 1);
});
test('restart marks an unfinished job interrupted instead of replaying or claiming success', async t => {
  const service = await fixture(t);
  service.state.jobs = [{ id: 'old', group_id: 'rain', status: 'running', progress: 31 }];
  await service.save(); await service.close();
  await service.init({ timer: false });
  assert.equal(service.state.jobs[0].status, 'interrupted');
  assert.equal(service.state.jobs[0].progress, 31);
});
test('another server cannot own the same update workspace', async t => {
  const service = await fixture(t);
  const second = new DataUpdates({ root: service.root, directory: service.directory, groups: service.groups });
  await assert.rejects(second.init({ timer: false }), /Another admin update worker/);
});

test('regional readiness reports the actual publication scope', async t => {
  const service = await fixture(t);
  service.groups[0] = { id: 'rain', kind: 'regional', full_requires: ['store'], requires: [] };
  assert.equal((await service.snapshot()).groups[0].mode, 'published-append');
  await fs.mkdir(path.join(service.root, 'store'));
  assert.equal((await service.snapshot()).groups[0].mode, 'full-refresh');
});

test('an enabled schedule can be disabled after its inputs disappear', async t => {
  const service = await fixture(t);
  await service.schedule('rain', 1);
  service.groups[0].requires = ['missing'];
  await assert.rejects(service.schedule('rain', 7), /Required local inputs/);
  await service.schedule('rain', 0);
  assert.equal(service.state.schedules.rain.next_run, null);
});
