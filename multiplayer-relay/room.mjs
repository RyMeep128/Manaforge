// Transport-only room. Never parses gameplay states or broadcasts private payloads.
import { Buffer } from 'node:buffer';
export const MAX_BYTES = 1048576;
export const CODE = /^[A-HJ-NP-Z2-9]{12}$/;
export class Room {
  constructor(peers = [], now = () => Date.now()) {
    this.peers = new Map(peers.map(p => [p.id, p])); this.now = now;
  }
  send(peer, message) {
    const raw = JSON.stringify({ relay_version: 1, ...message });
    if (Buffer.byteLength(raw) > 1500000 || peer.socket.bufferedAmount > 2 * MAX_BYTES) throw Error('SLOW_CONSUMER');
    peer.socket.send(raw);
  }
  receive(peer, raw) {
    try {
      if (typeof raw !== 'string' || Buffer.byteLength(raw) > 1500000) throw Error('FRAME_SIZE');
      const m = JSON.parse(raw);
      if (!m || m.relay_version !== 1) throw Error('RELAY_VERSION');
      const now = this.now();
      if (now - (peer.window ?? 0) > 1000) { peer.window = now; peer.count = 0; }
      if ((peer.count = (peer.count ?? 0) + 1) > 100) throw Error('RATE_LIMIT');
      if (!peer.role) {
        if (m.op === 'create' && this.peers.size === 0) {
          peer.role = 'host'; peer.id = 'host'; peer.created = now; peer.started = false;
        } else if (m.op === 'join') {
          const host = this.peers.get('host');
          if (!host || host.started || this.peers.has('guest') || now - host.created > 1800000) throw Error('ROOM_UNAVAILABLE');
          peer.role = 'guest'; peer.id = 'guest'; peer.created = now;
        } else throw Error('ROOM_UNAVAILABLE');
        this.peers.set(peer.id, peer); peer.save?.();
        this.send(peer, { op: 'admitted', peer: peer.id });
        if (peer.role === 'guest') this.send(this.peers.get('host'), { op: 'joined', peer: 'guest' });
        return;
      }
      if (m.op === 'start' && peer.role === 'host') { peer.started = true; peer.save?.(); return; }
      if (m.op === 'kick' && peer.role === 'host') { const guest = this.peers.get('guest'); if (guest) this.leave(guest); return; }
      if (m.op !== 'send' || m.payload === undefined) throw Error('MESSAGE_UNSUPPORTED');
      const target = this.peers.get(peer.role === 'host' ? 'guest' : 'host');
      if (!target) throw Error('PEER_UNAVAILABLE');
      this.send(target, { op: 'message', peer: peer.id, payload: m.payload });
    } catch (error) {
      const code = /^[A-Z_]+$/.test(error.message) ? error.message : 'INVALID_MESSAGE';
      console.warn('RELAY_' + code);
      try { this.send(peer, { op: 'error', code }); } catch {}
      this.leave(peer, code);
    }
  }
  leave(peer, code = 'GAME_INTERRUPTED') {
    if (peer.role && this.peers.get(peer.id) !== peer) return;
    if (peer.role) this.peers.delete(peer.id);
    try { peer.socket.close(1000, code); } catch {}
    // Rejected/unadmitted sockets never own a seat and cannot interrupt a match.
    if (!peer.role) return;
    const host = this.peers.get('host');
    if (peer.role === 'host' || host?.started) {
      for (const other of [...this.peers.values()]) { this.peers.delete(other.id); try { this.send(other, { op: 'closed', code }); } catch {} try { other.socket.close(1000, code); } catch {} }
    } else if (peer.role === 'guest' && host) {
      try { this.send(host, { op: 'left', peer: 'guest' }); } catch { this.leave(host); }
    }
  }
}
