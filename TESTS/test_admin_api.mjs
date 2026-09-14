import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';

test('data updates need no sign-in but require same origin and an allowlisted group', { timeout: 20000 }, async t => {
  const reservation = net.createServer();
  reservation.listen(0, '127.0.0.1'); await once(reservation, 'listening');
  const port = reservation.address().port; await new Promise(resolve => reservation.close(resolve));
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), 'uz-admin-api-'));
  const password = crypto.randomBytes(24).toString('hex');
  const child = spawn(process.execPath, ['server.mjs'], { cwd: new URL('../', import.meta.url),
    env: { ...process.env, NODE_ENV: 'production', PORT: String(port), UZGEODATA_WORKSPACE: workspace,
      ADMIN_USERNAME: 'test-admin', ADMIN_PASSWORD: password }, stdio: ['ignore', 'pipe', 'pipe'] });
  t.after(async () => { if (child.exitCode === null) { child.kill(); await once(child, 'exit'); } await fs.rm(workspace, { recursive: true, force: true }); });
  await Promise.race([once(child.stdout, 'data'), once(child, 'exit').then(() => { throw Error('Test admin server failed to start'); })]);
  const base = `http://127.0.0.1:${port}`;
  const request = (url, body, extra = {}) => fetch(base + url, { method: 'POST',
    headers: { 'Content-Type': 'application/json', ...extra }, body: JSON.stringify(body) });
  const inventory = await fetch(base + '/api/admin/variables');
  assert.equal(inventory.status, 200);
  const data = await inventory.json(); assert.ok(data.rows.length >= 281); assert.equal(data.operations.worker, 'local');
  assert.equal((await request('/api/admin/variables/update', { group_id: 'arbitrary-shell-command' })).status, 400);
  assert.equal((await request('/api/admin/variables/update', { group_id: 'regional-snow' }, { Origin: 'https://other.example' })).status, 403);
  assert.equal((await fetch(base + '/api/admin/variables/update', { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: 'regional-snow' })).status, 415);
  const alias = await fetch(base + '/admin', { redirect: 'manual' });
  assert.equal(alias.headers.get('location'), '/admin.html');
  // The dataset repository keeps its sign-in.
  assert.equal((await fetch(base + '/api/admin/datasets')).status, 401);
  assert.equal((await request('/api/admin/login', { username: 'test-admin', password: 'wrong' })).status, 401);
  assert.equal((await request('/api/admin/login', { username: 'test-admin', password })).status, 200);
});
