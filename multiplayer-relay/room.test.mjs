import test from 'node:test';
import assert from 'node:assert/strict';
import { Room } from './room.mjs';
function makePeer() {
  const p = { messages: [], closed: false };
  p.socket = { bufferedAmount: 0, send(raw) { p.messages.push(JSON.parse(raw)); }, close() { p.closed = true; } };
  return p;
}
const send = (room, peer, op, fields = {}) => room.receive(peer, JSON.stringify({ relay_version: 1, op, ...fields }));
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
test('lobby departure reopens admission; game departure interrupts everyone', () => {
  const room = new Room(); const host = makePeer(), guest = makePeer(), replacement = makePeer();
  send(room, host, 'create'); send(room, guest, 'join'); room.leave(guest);
  send(room, replacement, 'join'); assert.equal(replacement.role, 'guest');
  send(room, host, 'start'); room.leave(replacement); assert.equal(host.closed, true); assert.equal(room.peers.size, 0);
});
test('hibernation restores routing and started admission lock', () => {
  let room = new Room(); const host = makePeer(), guest = makePeer();
  send(room, host, 'create'); send(room, guest, 'join'); send(room, host, 'start');
  room = new Room([host, guest]); guest.messages = [];
  send(room, host, 'send', { payload: 'still private' }); assert.equal(guest.messages[0].payload, 'still private');
  const third = makePeer(); send(room, third, 'join'); assert.equal(third.closed, true);
  assert.equal(host.closed, false); assert.equal(guest.closed, false);
  assert.equal(room.peers.size, 2);
});
test('expiry, invalid frames and slow consumers fail closed', () => {
  let now = 1000; const room = new Room([], () => now), host = makePeer(), guest = makePeer();
  send(room, host, 'create'); now += 1800001; send(room, guest, 'join'); assert.equal(guest.closed, true);
  const invalid = makePeer(); room.receive(invalid, '{'); assert.equal(invalid.closed, true);
  const room2 = new Room(), h = makePeer(), g = makePeer(); send(room2, h, 'create'); send(room2, g, 'join');
  g.socket.bufferedAmount = 3 * 1048576; send(room2, h, 'send', { payload: 'bounded' }); assert.equal(h.closed, true); assert.equal(g.closed, true);
});
