import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';

const ACTIVE = new Set(['queued', 'running']);
const MAX_LOG = 24000;
const MAX_MS = 10 * 60 * 1000;

export const CHECKS = [
  { id: 'release', label: 'Release integrity', description: 'Check every file of the current atlas release (latest.json) against its manifest digests.', args: ['-m', 'qa.release_integrity'] },
  { id: 'topology', label: 'Upstream topology', description: 'Recalculate Syr Darya level 7 upstream membership and area.', args: ['qa/data_audit/check_syr_darya_level07.py'] },
  { id: 'climate', label: 'Raster to basin climate', description: 'Recalculate one basin-month of ERA5-Land temperature and precipitation.', args: ['qa/deep_dive/climate/check_one_basin.py'] },
  { id: 'screenshot', label: 'Monthly record and provisional estimate', description: 'Recalculate AET history, the January 2026 provisional estimate and its 2020–2025 holdout for basin 4121292070.', args: ['qa/deep_dive/tab_audit/check_screenshot_basin.py'] },
  { id: 'drought', label: 'Drought record', description: 'Check the served water-year totals, 1991–2020 normal, anomalies and SPI-12 for basin 4121292070 with an independent gamma estimator.', args: ['qa/deep_dive/drought/check_drought_basin.py'] },
  { id: 'catchment', label: 'Catchment statistics', description: 'Retrace the 89-basin catchment of 4121292070 and recalculate its area, relief, shape and monthly coverage.', args: ['qa/deep_dive/other_tabs/check_catchment_basin.py'] },
  { id: 'estimates', label: 'Independent estimates vs monthly record', description: 'Recompute 2003–2025 TerraClimate v1.1 normals for all 7,445 basins and compare them with the published independent estimates.', args: ['qa/deep_dive/other_tabs/check_estimate_versions.py'] },
  { id: 'model', label: 'Pskem model validation', description: 'Refit the published retrospective model and check the held-out baseline.', args: ['qa/model_validation/check_pskem.py'] },
];

export function pythonCheckRunner(root, python = process.env.UZGEODATA_PYTHON || 'python') {
  return (check, onOutput) => new Promise((resolve, reject) => {
    const child = spawn(python, check.args, { cwd: root, stdio: ['ignore', 'pipe', 'pipe'], shell: false });
    let done = false;
    const timer = setTimeout(() => { child.kill(); }, MAX_MS);
    for (const stream of [child.stdout, child.stderr]) stream.on('data', chunk => onOutput(chunk.toString('utf8')));
    child.on('error', error => { if (!done) { done = true; clearTimeout(timer); reject(new Error(`Could not launch Python: ${error.message}`)); } });
    child.on('close', code => { if (!done) { done = true; clearTimeout(timer); resolve({ code, timedOut: child.killed }); } });
  });
}

export class AgentRuns {
  constructor({ root, directory, checks = CHECKS, run = pythonCheckRunner(root), now = () => new Date().toISOString() }) {
    this.root = root; this.directory = directory; this.checks = checks; this.run = run; this.now = now;
    this.file = path.join(directory, 'state.json'); this.jobs = []; this.busy = false; this.saving = Promise.resolve();
  }
  async init() {
    await fs.mkdir(this.directory, { recursive: true });
    try { this.jobs = JSON.parse(await fs.readFile(this.file, 'utf8')).jobs || []; }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    for (const job of this.jobs) if (ACTIVE.has(job.status)) {
      job.status = 'interrupted'; job.finished_at = this.now(); job.message = 'Local server stopped during this run.';
    }
    await this.save(); return this;
  }
  async save() {
    const content = JSON.stringify({ version: 1, jobs: this.jobs }, null, 2);
    this.saving = this.saving.then(async () => {
      const temp = this.file + '.tmp'; await fs.writeFile(temp, content); await fs.rename(temp, this.file);
    });
    return this.saving;
  }
  snapshot() { return { worker: 'local', checks: this.checks.map(({ id, label, description }) => ({ id, label, description })), jobs: this.jobs, server_time: this.now() }; }
  async enqueue(id) {
    const check = this.checks.find(item => item.id === id);
    if (!check) throw Object.assign(new Error('Unknown agent'), { status: 400 });
    const existing = this.jobs.find(job => job.check_id === id && ACTIVE.has(job.status));
    if (existing) return existing;
    const job = { id: crypto.randomUUID(), check_id: id, label: check.label, status: 'queued', created_at: this.now(), message: 'Waiting for the local runner', log: '' };
    this.jobs.unshift(job); this.jobs = this.jobs.slice(0, 40);
    await this.save(); this.drain().catch(error => console.error('Agent runner:', error));
    return job;
  }
  async drain() {
    if (this.busy) return;
    this.busy = true;
    try {
      let job;
      while ((job = [...this.jobs].reverse().find(item => item.status === 'queued'))) {
        job.status = 'running'; job.started_at = this.now(); job.message = 'Recalculating evidence'; await this.save();
        try {
          const result = await this.run(this.checks.find(item => item.id === job.check_id), chunk => {
            job.log = (job.log + chunk).slice(-MAX_LOG);
            job.message = job.log.trim().split(/\r?\n/).at(-1)?.slice(0, 300) || 'Recalculating evidence';
          });
          job.status = result.timedOut ? 'failed' : result.code === 0 ? 'succeeded' : 'failed';
          job.exit_code = result.code;
          if (result.timedOut) job.message = 'Timed out after 10 minutes';
          else if (result.code !== 0 && !job.log) job.message = `Check exited with code ${result.code}`;
        } catch (error) { job.status = 'failed'; job.message = error.message.slice(0, 300); }
        job.finished_at = this.now(); await this.save();
      }
    } finally { this.busy = false; }
  }
  async close() { await this.saving; }
}
