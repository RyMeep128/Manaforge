import test from 'node:test';
import assert from 'node:assert/strict';
import { Room } from './room.mjs';
function makePeer() {
  const p = { messages: [], closed: false };
  p.socket = { bufferedAmount: 0, send(raw) { p.messages.push(JSON.parse(raw)); }, close(code, reason) { p.closed = true; p.closeReason = reason; } };
  return p;
}
const send = (room, peer, op, fields = {}) => room.receive(peer, JSON.stringify({ relay_version: 1, ...(op === 'create' ? { recovery_version: 1 } : {}), op, ...fields }));
test('private payloads route only to the other admitted endpoint', () => {
  const room = new Room(); const host = makePeer(), guest = makePeer(), stranger = makePeer();
  send(room, host, 'create'); send(room, guest, 'join'); send(room, stranger, 'join');
  assert.equal(stranger.closed, true); assert.equal(room.peers.size, 2);
  host.messages = []; guest.messages = [];
  send(room, host, 'send', { payload: { private_hand: 'guest only' } });
  assert.equal(host.messages.length, 0); assert.equal(guest.messages[0].payload.private_hand, 'guest only');
  assert.equal(stranger.messages.some(m => m.payload), false);
});
test('guests cannot start, kick or replace the host', () => {
  for (const op of ['start', 'kick', 'create']) {
    const room = new Room(); const host = makePeer(), guest = makePeer();
    send(room, host, 'create'); send(room, guest, 'join'); send(room, guest, op);
    assert.equal(guest.closed, true); assert.equal(host.closed, false); assert.equal(room.peers.get('host'), host);
  }
});
test('guest departure preserves an active match and reopens admission', () => {
  const room = new Room(); const host = makePeer(), guest = makePeer(), replacement = makePeer();
  send(room, host, 'create'); send(room, guest, 'join'); room.leave(guest);
  send(room, replacement, 'join'); assert.equal(replacement.role, 'guest');
  send(room, host, 'start'); room.leave(replacement); assert.equal(host.closed, false); assert.equal(room.peers.size, 1);
  const returning = makePeer(); send(room, returning, 'join'); assert.equal(returning.role, 'guest');
  room.leave(host); assert.equal(returning.closed, true); assert.equal(room.peers.size, 0);
});
test('hibernation restores private routing and active seat-picker admission', () => {
  let room = new Room(); const host = makePeer(), guest = makePeer();
  send(room, host, 'create'); send(room, guest, 'join'); send(room, host, 'start');
  room = new Room([host, guest]); guest.messages = [];
  send(room, host, 'send', { payload: 'still private' }); assert.equal(guest.messages[0].payload, 'still private');
  const third = makePeer(); send(room, third, 'join'); assert.equal(third.closed, false);
  send(room, host, 'send', { peer: third.id, payload: 'public seat list' });
  assert.equal(third.messages.at(-1).payload, 'public seat list');
  assert.equal(guest.messages.at(-1).payload, 'still private');
  assert.equal(host.closed, false); assert.equal(guest.closed, false);
  assert.equal(room.peers.size, 3);
});
test('expiry, invalid frames and slow consumers fail closed', () => {
  let now = 1000; const room = new Room([], () => now), host = makePeer(), guest = makePeer();
  send(room, host, 'create'); now += 1800001; send(room, guest, 'join'); assert.equal(guest.closed, true);
  const invalid = makePeer(); room.receive(invalid, '{'); assert.equal(invalid.closed, true);
  const room2 = new Room(), h = makePeer(), g = makePeer(); send(room2, h, 'create'); send(room2, g, 'join');
  g.socket.bufferedAmount = 3 * 1048576; send(room2, h, 'send', { payload: 'bounded' }); assert.equal(h.closed, false); assert.equal(g.closed, true);
});

test('both endpoints retain the rejection cause in error and close frames', () => {
  const room = new Room(), host = makePeer(), guest = makePeer();
  send(room, host, 'create'); send(room, guest, 'join'); send(room, host, 'start');
  room.receive(guest, '{');
  assert.equal(guest.messages.at(-1).code, 'INVALID_MESSAGE');
  assert.equal(host.messages.at(-1).code, 'INVALID_MESSAGE');
  assert.equal(guest.closeReason, 'INVALID_MESSAGE');
  assert.equal(host.closed, false);
  assert.equal(host.messages.at(-1).op, 'left');
  assert.equal(room.peers.size, 1);
});

test('active rooms remain joinable after lobby expiry and candidate traffic stays isolated', () => {
  let now = 0; const room = new Room([], () => now), host = makePeer(), guest = makePeer();
  send(room, host, 'create'); send(room, guest, 'join'); send(room, host, 'start'); now = 1800001;
  const candidate = makePeer(); send(room, candidate, 'join'); assert.equal(candidate.closed, false);
  send(room, host, 'send', { payload: 'private-hand' });
  assert.equal(guest.messages.at(-1).payload, 'private-hand');
  assert.equal(candidate.messages.some(m => m.payload === 'private-hand'), false);
  room.leave(candidate); send(room, host, 'send', { peer: candidate.id, payload: 'racing-list' });
  assert.equal(host.closed, false); assert.equal(guest.closed, false);
});

test('legacy hosts keep their original active-game admission lock', () => {
  const room = new Room(), host = makePeer(), guest = makePeer(), candidate = makePeer();
  send(room, host, 'create', { recovery_version: 0 });send(room, guest, 'join');send(room, host, 'start');send(room, candidate, 'join');
  assert.equal(candidate.closed, true);assert.equal(host.closed, false);assert.equal(guest.closed, false);
});
