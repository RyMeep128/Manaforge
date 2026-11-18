import http from 'node:http';
import { WebSocketServer } from 'ws';
import { Room, CODE, MAX_BYTES } from './room.mjs';
const rooms = new Map();
const server = http.createServer((_, res) => { res.writeHead(404); res.end(); });
const wss = new WebSocketServer({ noServer: true, maxPayload: 1500000, perMessageDeflate: false });
const attempts = new Map();
server.on('upgrade', (req, socket, head) => {
  const url = new URL(req.url, 'http://localhost'); const code = url.searchParams.get('room');
  const ip = socket.remoteAddress; const window = Math.floor(Date.now() / 60000);
  const a = attempts.get(ip); const count = a?.window === window ? a.count + 1 : 1; attempts.set(ip, { window, count });
  if (url.pathname !== '/v1/socket' || !CODE.test(code ?? '') || count > 30 || rooms.size >= 1000 && !rooms.has(code)) { socket.destroy(); return; }
  wss.handleUpgrade(req, socket, head, ws => {
    if (!rooms.has(code)) rooms.set(code, new Room()); const room = rooms.get(code);
    const peer = { socket: ws }; const admission = setTimeout(() => { if (!peer.role) ws.close(1008); }, 10000);
    ws.on('message', (data, binary) => room.receive(peer, binary ? null : data.toString('utf8')));
    ws.on('close', () => { clearTimeout(admission); room.leave(peer); if (!room.peers.size) rooms.delete(code); });
    ws.on('error', () => room.leave(peer));
  });
});
setInterval(() => {
  const now = Date.now();
  for (const [ip, a] of attempts) if (a.window < Math.floor(now / 60000)) attempts.delete(ip);
  for (const room of rooms.values()) { const host = room.peers.get('host'); if (host && now - host.created > (host.started ? 21600000 : 1800000)) room.leave(host); }
}, 30000).unref();
server.listen(Number(process.env.PORT ?? 8787), process.env.HOST ?? '127.0.0.1');
