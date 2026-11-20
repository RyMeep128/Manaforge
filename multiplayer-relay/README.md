# Manaforge multiplayer relay

The relay transports private, targeted messages for a two-player match. Active
rooms also admit up to two waiting joiners to choose an available seat. Only the
host supplies their public seat lists and grants a seat; private gameplay frames
are explicitly targeted to the selected guest and never broadcast.
XMage and Java run on the hosting computer. The relay never runs gameplay rules,
loads an engine, or stores decks, snapshots, or match history.

The default shared origin is
`wss://manaforge-multiplayer-relay.rshafer128.workers.dev`.

## Shared Cloudflare deployment

Use an account on **Workers Free**. A Free domain plan does not establish the
account's Workers subscription. Verify under Manage Account → Billing →
Subscriptions before deployment. Do not upgrade Workers to enable this relay.

```powershell
cd multiplayer-relay
npm ci
npx wrangler login
npx wrangler deploy --dry-run
npm run deploy
```

The deploy creates a Worker and a SQLite-backed Durable Object namespace. It uses
the supplied `workers.dev` hostname, so no purchased domain is required. Copy the
printed HTTPS origin, change `https://` to `wss://`, and enter it under Play's relay
settings. Every player can host through that deployment without an account.

The Free plan has hard account-wide quotas, shared with any other Workers and
Durable Objects on the account. As of November 2026, Workers and Durable Objects
each include 100,000 requests/day; Durable Objects include 13,000 GB-s/day. Incoming
WebSocket messages use a 20:1 request-billing ratio. Hibernation avoids keeping an
idle room active. This is a bounded free service, not an unlimited availability
promise. Quota exhaustion interrupts service instead of authorizing a paid tier.
See [current pricing](https://developers.cloudflare.com/durable-objects/platform/pricing/).

The Worker retains only socket attachments and a cleanup alarm. Lobby admission
expires after 30 minutes; active rooms close after six hours. Do not log payloads
or enable paid logging/storage products for this deployment. Deployments and
infrastructure restarts can close connections. Guest loss preserves the host's
room and engine, allowing reconnects and AI replacement. Losing the host's relay
connection still closes the room; there is no host migration. Updated clients
require the relay's `recovery_version: 1` admission capability.

## Standalone custom relay

```powershell
cd multiplayer-relay
npm ci --omit=dev
npm start
```

The default listener is `127.0.0.1:8787`. Set `HOST` and `PORT` for your hosting
environment. Put the service behind an existing HTTPS reverse proxy with a valid
certificate, WebSocket upgrades enabled, and idle timeouts long enough for turns.
Forward `/v1/socket` and its query string unchanged. The standalone software is
free; your server, domain, or proxy provider may charge for hosting.

Both players select the same WSS origin and use a join code, or paste a copied
Manaforge invitation containing the origin and code. Custom servers must implement
this protocol; an arbitrary WebSocket echo server is insufficient. Manaforge never
disables certificate verification. `MANAFORGE_RELAY_DEVELOPMENT=1` allows `ws://`
only on loopback for development. `MANAFORGE_RELAY_URL` supplies an initial default
before a user saves their relay setting.

## Relay protocol v1

Connect to `WSS_ORIGIN/v1/socket?room=CODE`, where CODE is 12 uppercase characters
from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`. The first message must arrive within ten
seconds and contain `{"relay_version":1,"op":"create"}` for a host, or `join` for
a guest. Room creation is exclusive. The host's admitted socket is its authority;
there is no host takeover or reconnect token.

Responses include `admitted` with `peer: host|guest`, and host notifications
`joined`/`left`. Use `{"relay_version":1,"op":"send","payload":...}` to send only
to the other admitted peer. Incoming messages use `op: message`, the authenticated
sender's `peer`, and `payload`. A client cannot choose another sender or recipient.

Only hosts can send `start` to lock admission or `kick` to remove the guest before
starting. A guest leaving a lobby reopens admission; a host leaving or any player
leaving an active room closes the room. Protocol failures return `error` with a
safe code and close the offending connection. `closed` with `GAME_INTERRUPTED`
informs surviving peers about active-game loss.

Payloads carry lobby controls, a seat-only launch bootstrap, or base64-encoded
gameplay frames. Gameplay frames retain the existing 1 MiB limit. Relay envelopes
are limited to 1.5 MB to allow base64 overhead; queues and message rates are
bounded. Gateway challenge authentication still takes place through the tunnel.
WSS protects each connection; relay operators are trusted with transported data.

Tests run in GitHub Actions: the same adapter contract exercises standalone Node
and the Cloudflare local runtime, alongside routing, expiry, hibernation-restoration,
and abuse checks. Successful relay tests do not establish a complete Unity game.
