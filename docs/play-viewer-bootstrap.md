# Private Unity viewer bootstrap

Status: typed export/parse boundary at 0.5.91-alpha.1. Inherited delivery,
deadline/EOF handling, OS child containment and production mounting remain open.

The Python `export_viewer_bootstrap` function returns at most 16 KiB of private
UTF-8 bytes for one viewer. `Protocol.ViewerBootstrap.Parse` consumes the same
shape in Unity. A shared version 1 schema and public synthetic fixtures specify
the contract. This is distinct from the gateway-only all-decks launch manifest
and from public game protocol messages. No deck model or game rule is added.

Fields are bootstrap/protocol versions, IPv4 loopback literal and port, session
and viewer IDs, expected engine version/artifact pin, one 32-byte viewer key, and
optional artwork directory/manifest pin. Only `127.0.0.1` is accepted initially;
DNS names and public bind addresses are rejected. IDs are opaque context, not
seat counts or controller types. Optional artwork metadata requires a fully
qualified local path and SHA-256 pin; relative and UNC/network paths are refused.
Schema validates shape; platform path qualification and the byte cap are runtime
checks. The exporter performs no file access, socket connection or key generation.

The launcher must generate a fresh viewer-only cryptographic key and deliver
bootstrap through an inherited private channel. Never put runtime bytes in
arguments, environment variables, logs, screenshots, artifacts or configuration
files. Never reuse a gateway-owner key or give Unity another seat's credentials.
The caller remains responsible for provenance and secure ownership of that
channel. Parsing does not authenticate the launcher or gateway, verify installed
artifacts, grant gameplay authority or prove startup readiness.

Unity stores an owned key buffer. `TakeViewerKey` transfers it once, atomically;
the next owner must clear it after use. Dispose clears an unclaimed key and
revokes later transfer. Transferred buffers remain caller-owned. ToString returns
only a fixed private marker; validation failures expose a fixed error code.
Caller input bytes remain caller-owned and should be cleared when possible.
JSON/UTF-8 conversion creates managed strings, so this does not promise secure
erasure of every runtime copy. Exported Python bytes are immutable as well.

Bootstrap deliberately contains no prebuilt hello proofs/nonces. Fresh challenge
exchange and the existing role-bound handshake remain separate requirements;
reconnecting must not replay captured authentication material. Artwork pins feed
the existing CoreArtworkBundle reader only after trusted bootstrap provenance is
established. No private pipe, launcher command or real connection is created by
this increment, and G0/G1 acceptance remains open.

Focused local evidence: 14 Python checks and 326 Unity EditMode checks including
existing Java protocol preflight. Both languages consume the shared synthetic
fixture; negatives reject unknown owner/deck fields, invalid versions/IDs/keys,
public/DNS endpoints and invalid ports. Unity checks include duplicate JSON,
malformed UTF-8/BOM/size limits, optional artwork metadata, disposal and concurrent
single-use key transfer. All committed credentials/pins are public fake vectors.
The public scene is unchanged; no new owner UI verification is needed. No full
application suite ran. CI review remains every third implementation commit, next
at 0.5.93; no current CI success is claimed for this increment.
