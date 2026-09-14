import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';

const DAY = 86400000;
const ACTIVE = new Set(['queued', 'running']);

export function pythonRunner(root, python = process.env.UZGEODATA_PYTHON || 'python') {
  return (group, progress) => new Promise((resolve, reject) => {
    // Only a registry id is passed. No shell and no client-supplied command/arguments.
    const child = spawn(python, ['PIPELINES/run_data_update.py', group.id], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
    let buffer = '', failure = null;
    child.stdout.on('data', chunk => {
      buffer += chunk.toString();
      if (buffer.length > 65536) buffer = buffer.slice(-65536);
      const lines = buffer.split('\n'); buffer = lines.pop();
      for (const line of lines) {
        try {
          const event = JSON.parse(line);
          if (event.type === 'progress') progress(event);
          if (event.type === 'failure') failure = event.message;
        } catch { /* Pipeline stdout is not an instruction or job-state update. */ }
      }
    });
    // Detailed pipeline logs are private WORKSPACE files, never copied to the site.
    child.stderr.on('data', () => {});
    child.on('error', () => reject(new Error('Could not start Python. Configure UZGEODATA_PYTHON for the pipeline environment.')));
    child.on('close', code => code === 0 ? resolve() : reject(new Error(failure || `Update exited with code ${code}. See the private update log in WORKSPACE/data-updates/logs.`)));
  });
}

export class DataUpdates {
  constructor({ root, directory, groups, run = pythonRunner(root), now = () => Date.now() }) {
    this.root = root; this.directory = directory; this.groups = groups; this.run = run; this.now = now;
    this.file = path.join(directory, 'state.json'); this.state = { version: 1, jobs: [], schedules: {} };
    this.busy = false; this.saving = Promise.resolve();
  }

  async init({ timer = true } = {}) {
    await fs.mkdir(this.directory, { recursive: true });
    this.lock = path.join(this.directory, 'worker.lock');
    try {
      const owner = Number(await fs.readFile(this.lock, 'utf8'));
      let alive = false;
      try { process.kill(owner, 0); alive = true; } catch (error) { alive = error.code !== 'ESRCH'; }
      if (alive) throw Error('Another admin update worker is already using this workspace.');
      await fs.unlink(this.lock);
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    await fs.writeFile(this.lock, String(process.pid), { flag: 'wx' });
    try { this.state = JSON.parse(await fs.readFile(this.file, 'utf8')); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    // A process restart is not success. Preserve the audit trail and don't replay work blindly.
    for (const job of this.state.jobs) if (ACTIVE.has(job.status)) {
      job.status = 'interrupted'; job.finished_at = this.iso(); job.message = 'Admin server stopped before this job completed. Review the checkpoint before retrying.';
    }
    await this.save();
    if (timer) { this.timer = setInterval(() => this.tick().catch(error => console.error('Update scheduler:', error.message)), 60000); this.timer.unref(); }
    return this;
  }

  iso() { return new Date(this.now()).toISOString(); }
  group(id) {
    const group = this.groups.find(item => item.id === id);
    if (!group) throw Object.assign(new Error('Unknown update group'), { status: 400 });
    return group;
  }
  async save() {
    const content = JSON.stringify(this.state, null, 2);
    this.saving = this.saving.then(async () => {
      const temp = this.file + '.tmp'; await fs.writeFile(temp, content); await fs.rename(temp, this.file);
    });
    return this.saving;
  }
  async availability(group) {
    const missing = [];
    for (const relative of group.requires || []) {
      try { await fs.access(path.join(this.root, relative)); } catch { missing.push(relative); }
    }
    return { ready: missing.length === 0, reason: missing.length ? `Required local inputs are missing: ${missing.join(', ')}. See the admin setup guide.` : null };
  }
  async snapshot() {
    return { jobs: this.state.jobs, schedules: this.state.schedules,
      groups: await Promise.all(this.groups.map(async group => ({ id: group.id, label: group.label,
        interval_days: group.interval_days, note: group.note, ...await this.availability(group) }))),
      worker: 'local', server_time: this.iso(),
      note: 'Automatic updates run while this admin server is running. Successful jobs update local data; deploying the public site is a separate step.' };
  }
  async enqueue(id, trigger = 'manual') {
    const group = this.group(id);
    const existing = this.state.jobs.find(job => job.group_id === id && ACTIVE.has(job.status));
    if (existing) return existing;
    const available = await this.availability(group);
    if (!available.ready) throw Object.assign(new Error(available.reason), { status: 409 });
    // Recheck after async preflight: two simultaneous requests must produce one job.
    const concurrent = this.state.jobs.find(job => job.group_id === id && ACTIVE.has(job.status));
    if (concurrent) return concurrent;
    const job = { id: crypto.randomUUID(), group_id: id, label: group.label, trigger, status: 'queued',
      progress: 0, created_at: this.iso(), message: 'Waiting for the update worker' };
    this.state.jobs.unshift(job);
    this.state.jobs = this.state.jobs.filter((item, index) => index < 100 || ACTIVE.has(item.status));
    await this.save();
    this.drain().catch(error => console.error('Update worker:', error.message));
    return job;
  }
  async drain() {
    if (this.busy) return;
    this.busy = true;
    try {
      let job;
      while ((job = [...this.state.jobs].reverse().find(item => item.status === 'queued'))) {
        job.status = 'running'; job.started_at = this.iso(); job.message = 'Checking update prerequisites'; await this.save();
        try {
          await this.run(this.group(job.group_id), event => {
            job.progress = Math.max(job.progress, Math.min(99, Math.max(0, Number(event.progress) || 0)));
            job.message = String(event.message || 'Updating').slice(0, 500);
          });
          job.status = 'succeeded'; job.progress = 100; job.message = 'Local data updated. Review coverage before deploying.';
        } catch (error) { job.status = 'failed'; job.message = error.message.slice(0, 700); }
        job.finished_at = this.iso(); await this.save();
      }
    } finally { this.busy = false; }
  }
  async schedule(id, days) {
    const group = this.group(id);
    if (![0, 1, 7, 30].includes(days)) throw Object.assign(new Error('Choose off, daily, weekly or every 30 days'), { status: 400 });
    if (days) {
      const available = await this.availability(group);
      if (!available.ready) throw Object.assign(new Error(available.reason), { status: 409 });
    }
    this.state.schedules[id] = { days, next_run: days ? new Date(this.now() + days * DAY).toISOString() : null };
    await this.save(); return this.state.schedules[id];
  }
  async tick() {
    if (this.ticking) return;
    this.ticking = true;
    try {
      for (const [id, schedule] of Object.entries(this.state.schedules)) {
        if (!schedule.days || Date.parse(schedule.next_run) > this.now()) continue;
        // Advance first, including failures: avoid retrying an unavailable source every minute.
        schedule.next_run = new Date(this.now() + schedule.days * DAY).toISOString();
        delete schedule.error; await this.save();
        try { await this.enqueue(id, 'scheduled'); }
        catch (error) { schedule.error = error.message; await this.save(); }
      }
    } finally { this.ticking = false; }
  }
  async close() { clearInterval(this.timer); await this.saving; if (this.lock) await fs.unlink(this.lock).catch(() => {}); }
}
