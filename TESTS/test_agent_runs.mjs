import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { AgentRuns, CHECKS } from '../SERVER/agentRuns.mjs';

test('public reviewed snapshot covers each local validation check', async () => {
  const snapshot = JSON.parse(await fs.readFile(new URL('../PUBLISHED/data/agent-status.json', import.meta.url), 'utf8'));
  assert.deepEqual(snapshot.checks.map(check => check.id), CHECKS.map(check => check.id));
  assert.ok(snapshot.checks.every(check => check.status && check.summary));
  assert.ok(snapshot.findings.length && snapshot.findings.every(item => item.title && item.text));
  // Every check a rerun can launch is a file in the repository, never a free-form command.
  for (const check of CHECKS) {
    const script = check.args[0] === '-m' ? `${check.args[1].replaceAll('.', '/')}.py` : check.args[0];
    await fs.access(new URL(`../${script}`, import.meta.url));
  }
});

test('allowlisted checks run serially and persist their observed output', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'uzg-agent-'));
  let running = 0, maximum = 0;
  const run = async (check, output) => {
    running++; maximum = Math.max(maximum, running);
    output(`${check.id}: evidence checked\n`);
    await new Promise(resolve => setTimeout(resolve, 15));
    running--;
    return { code: check.id === 'bad' ? 1 : 0, timedOut: false };
  };
  const checks = [{ id: 'good', label: 'Good', description: '', args: [] }, { id: 'bad', label: 'Bad', description: '', args: [] }];
  try {
    const agents = await new AgentRuns({ root: directory, directory, checks, run }).init();
    await assert.rejects(agents.enqueue('unlisted'), /Unknown agent/);
    const first = await agents.enqueue('good');
    assert.equal((await agents.enqueue('good')).id, first.id);
    await agents.enqueue('bad');
    while (agents.snapshot().jobs.some(job => ['queued', 'running'].includes(job.status))) await new Promise(resolve => setTimeout(resolve, 10));
    assert.equal(maximum, 1);
    assert.equal(agents.snapshot().jobs.find(job => job.check_id === 'good').status, 'succeeded');
    assert.equal(agents.snapshot().jobs.find(job => job.check_id === 'bad').status, 'failed');
    assert.match(agents.snapshot().jobs[0].log, /evidence checked/);
    await agents.close();
    const reopened = await new AgentRuns({ root: directory, directory, checks, run }).init();
    assert.equal(reopened.snapshot().jobs.length, 2);
    await reopened.close();
  } finally { await fs.rm(directory, { recursive: true, force: true }); }
});

test('restart marks an unfinished run interrupted without replaying it', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'uzg-agent-'));
  try {
    await fs.writeFile(path.join(directory, 'state.json'), JSON.stringify({ jobs: [{ id: 'old', check_id: 'good', status: 'running' }] }));
    const agents = await new AgentRuns({ root: directory, directory, checks: [], run: () => { throw Error('Unexpected replay'); } }).init();
    assert.equal(agents.snapshot().jobs[0].status, 'interrupted');
    await agents.close();
  } finally { await fs.rm(directory, { recursive: true, force: true }); }
});
