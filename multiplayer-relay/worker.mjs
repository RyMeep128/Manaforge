import { DurableObject } from 'cloudflare:workers';
import { Room, CODE } from './room.mjs';
export class GameRoom extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    const peers = ctx.getWebSockets().map(socket => this.peer(socket));
    this.room = new Room(peers.filter(p => p.role));
    this.pending = new Map(peers.map(p => [p.socket, p]));
  }
  peer(socket) {
    const p = { ...socket.deserializeAttachment(), socket };
    p.save = () => { const { socket: _, save: __, ...attachment } = p; socket.serializeAttachment(attachment); };
    return p;
  }
  async fetch(request) {
    if (request.headers.get('Upgrade')?.toLowerCase() !== 'websocket') return new Response('WebSocket required', { status: 426 });
    if (this.ctx.getWebSockets().length >= 4) return new Response('Room full', { status: 429 });
    const pair = new WebSocketPair(); this.ctx.acceptWebSocket(pair[1]);
    pair[1].serializeAttachment({ connected: Date.now() });
    this.pending.set(pair[1], this.peer(pair[1]));
    await this.ctx.storage.setAlarm(Date.now() + 30000);
    return new Response(null, { status: 101, webSocket: pair[0] });
  }
  webSocketMessage(socket, message) { this.room.receive(this.pending.get(socket), message); }
  webSocketClose(socket) { const p = this.pending.get(socket); if (p) this.room.leave(p); this.pending.delete(socket); }
  webSocketError(socket) { this.webSocketClose(socket); }
  async alarm() {
    const now = Date.now();
    for (const [socket, p] of this.pending) {
      if ((!p.role && now - p.connected > 10000) || (p.role === 'host' && now - p.created > (p.started ? 21600000 : 1800000))) this.webSocketClose(socket);
    }
    if (this.room.peers.size) await this.ctx.storage.setAlarm(now + 1800000);
    else await this.ctx.storage.deleteAll();
  }
}
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== '/v1/socket' || !CODE.test(url.searchParams.get('room') ?? '')) return new Response('Invalid room', { status: 400 });
    const id = env.ROOMS.idFromName(url.searchParams.get('room'));
    return env.ROOMS.get(id).fetch(request);
  }
};
