// GitHub Actions only: exercise the same protocol over both real adapter endpoints.
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import WebSocket from 'ws';

function next(socket) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error('relay response timed out')), 10000);
    socket.once('message', raw => { clearTimeout(timer); resolve(JSON.parse(raw)); });
    socket.once('error', error => { clearTimeout(timer); reject(error); });
  });
}
async function open(url, op) {
  const socket = new WebSocket(url);
  await new Promise((resolve, reject) => { socket.once('open', resolve); socket.once('error', reject); });
  const response = next(socket); socket.send(JSON.stringify({ relay_version: 1, recovery_version: 1, op }));
  assert.equal((await response).op, 'admitted'); return socket;
}
for (const [adapter, port, command] of [
  ['standalone', 18787, ['server.mjs']],
  ['cloudflare-local', 18788, ['node_modules/wrangler/bin/wrangler.js', 'dev', '--local', '--ip', '127.0.0.1', '--port', '18788']]
]) {
  test(adapter + ' routes privately and preserves active rooms for reconnects', { timeout: 120000 }, async t => {
    const child = spawn(process.execPath, command, { env: { ...process.env, PORT: String(port), WRANGLER_SEND_METRICS: 'false' }, detached: process.platform !== 'win32', stdio: 'inherit' });
    const sockets = [];
    t.after(() => { for (const socket of sockets) socket.terminate(); if (process.platform !== 'win32') { try { process.kill(-child.pid, 'SIGTERM'); } catch {} } else child.kill(); });
    let ready = false;
    for (let i = 0; i < 200; i++) {
      if (child.exitCode !== null) throw Error('relay exited during startup');
      try { await fetch(`http://127.0.0.1:${port}/`); ready = true; break; } catch { await new Promise(r => setTimeout(r, 250)); }
    }
    assert.equal(ready, true);
    const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    const code = [...randomBytes(12)].map(b => alphabet[b % alphabet.length]).join('');
    const url = `ws://127.0.0.1:${port}/v1/socket?room=${code}`;
    const host = await open(url, 'create'); sockets.push(host);
    const joined = next(host); const guest = await open(url, 'join'); sockets.push(guest); assert.equal((await joined).op, 'joined');
    const receipt = next(guest); host.send(JSON.stringify({ relay_version: 1, op: 'send', payload: { type: 'frame', data: 'private-test' } }));
    const message = await receipt; assert.equal(message.peer, 'host'); assert.equal(message.payload.data, 'private-test');
    host.send(JSON.stringify({ relay_version: 1, op: 'start' }));
    const late = new WebSocket(url); sockets.push(late); await new Promise(r => late.once('open', r));
    const admitted = next(late), candidateJoined = next(host); late.send(JSON.stringify({ relay_version: 1, op: 'join' }));
    const candidate = await admitted; assert.equal(candidate.op, 'admitted'); assert.equal((await candidateJoined).peer, candidate.peer);
    const seats = next(late); host.send(JSON.stringify({ relay_version: 1, op: 'send', peer: candidate.peer, payload: 'public seats' })); assert.equal((await seats).payload, 'public seats');
    const disconnected = next(host); guest.close(); assert.equal((await disconnected).op, 'left');
    const stillHosted = next(late); host.send(JSON.stringify({ relay_version: 1, op: 'send', peer: candidate.peer, payload: 'still hosted' })); assert.equal((await stillHosted).payload, 'still hosted');
  });
}
