# Self-hosted Deck Library — stage 1

Manaforge stays local-first. Installing or launching the desktop app does not
start a server, connect to a library, create an online account, open router ports,
or install Cloudflare. There are no default library connections or developer
server addresses. Anyone can operate an independent library with its own users,
database, server UUID, and published deck IDs.

This first stage supplies a standalone JSON API, persistent SQLite storage,
invitation-only accounts, and revisioned publications. It is useful to operators
and API clients. It does **not** yet supply Browse Online, desktop connections,
Publish to Library, read-only follows, offline subscription caches, update
notifications, independent-copy UI, or installation/Settings hosting controls.
Those features are not exposed as partially working desktop actions.

## Architecture and remaining stages

`mtg_core.library.payload` projects the existing `mtg_core.decks.Deck` model into
an allowlist of shareable fields. `store` owns persistence and authorization;
`api` exposes a versioned WSGI application; `__main__` starts a separate Waitress
process. Nothing imports the desktop application or exposes desktop commands.
The optional Waitress dependency is separate from desktop requirements.

Reuse points for follow-up work:

1. Desktop client: separate transport and credential storage, multiple connections
   keyed by server UUID, shared `mtg_ui.jobs.JobQueue` for nonblocking work,
   `mtg_home.modules.MODULES`/Home and the existing editor for browsing and explicit
   publication. Reuse the card catalog and artwork cache for previews. Require
   HTTPS for remote connections; HTTP may be explicitly allowed on private LANs.
2. Offline following/copying: use `DeckDocument` and atomic `DeckStore` persistence,
   store `(server_id, deck_id, revision)` separately from local deck identity, keep
   follows read-only, stage updates before atomic replacement, and offer explicit
   acceptance. Copies need fresh local UUIDs and source attribution. Preserve
   existing local print statuses; new followed entries may start Pending locally.
3. Hosting UI: add a disabled-by-default **Host a Manaforge Deck Library** section
   to `mtg_ui.data_management.DataManagementDialog` (current first-run setup), and
   shared Settings controls. Configure storage, administrator, LAN/tunnel,
   background startup, health checks and repair without overwriting databases.
   Joining belongs exclusively in Browse Online. Skipping hosting must skip all
   server dependencies/configuration. Bundle/service lifecycle work remains here.

## Explicit operator setup

Source hosting currently requires Python 3.12+ and a configured Manaforge source
environment. From the repository root in PowerShell:

```powershell
python -m pip install -r requirements-library.txt
$env:PYTHONPATH = (Join-Path (Get-Location) 'Mtg_Projects/mtg_core')
$libraryData = Join-Path $env:LOCALAPPDATA 'ManaforgeLibrary/Friends'
python -m mtg_core.library --data-dir $libraryData init --name 'Friends' --admin administrator
python -m mtg_core.library --data-dir $libraryData serve
```

Use your environment's Python executable if it is not named `python`. On Linux,
set `PYTHONPATH` to `Mtg_Projects/mtg_core` and use a private data directory under
your home directory. The initializer prompts twice for a password (12–256
characters); credentials are never command-line arguments. Store the library
outside the checkout; initialization rejects source-tree storage and never
overwrites an existing database. No service starts during initialization.

The default bind is `127.0.0.1:8771`. For LAN-only use, explicitly supply
`serve --lan --host <your-private-LAN-IP>` and configure your firewall for trusted
devices only. Public and wildcard bind addresses are rejected. LAN HTTP is
unencrypted; use a TLS reverse proxy whenever the LAN is not trusted.

For remote access, configure **your own** Cloudflare Tunnel with its own credentials
outside the repository, mapping your HTTPS hostname to `http://127.0.0.1:8771`.
Keep the server on loopback. Do not forward router ports. Require HTTPS at the
tunnel edge and configure an optional Cloudflare access/IP policy if desired.
The application does not trust forwarded headers and does not derive identity
from Cloudflare; library authentication remains mandatory. Tunnel creation,
credentials, DNS and automatic background startup are operator-managed in this
stage. No tunnel binary or personal configuration is bundled.

Restrict the data directory to the service account using OS permissions (including
Windows ACLs). It contains the database and SQLite transaction files, not artwork
or user-named uploaded files. POSIX creation requests private permissions. Avoid
placing the directory on a shared drive. Run under an unprivileged account with
access only to that directory and the read-only application installation.

## API v1

All responses are JSON with `api_version: 1`. Errors include an understandable
`error` string and an HTTP status. Use `Authorization: Bearer <session-token>`
on every endpoint except info, login and invitation redemption. Sessions expire
after 24 hours. Protected endpoints validate active account/session membership
on each request. No cookies, cross-origin access, or public self-registration.

Requests containing bodies need `Content-Type: application/json` and a valid
Content-Length. Bodies are limited to 1 MiB, decks to 2000 entries/100 categories,
and metadata/list sizes are bounded. Waitress limits connections, headers, body
size and idle channels. Persistent throttles limit login/registration attempts
by peer and username and authenticated requests by token. Behind a loopback
tunnel, the peer throttle is shared across clients. Passwords use salted
PBKDF2-HMAC-SHA256 with 600,000 rounds. Session/invitation values are stored as
SHA-256 digests. Never put credentials in URLs or logs.

| Method/path under `/api/v1` | Body or result |
| --- | --- |
| `GET /info` | Library name, stable `server_id`, API version, request limit |
| `POST /login` | `{ "username": "...", "password": "..." }`; returns `token`, `expires_in` |
| `POST /logout` | Revoke current session immediately |
| `POST /invitations` | Administrator only; returns a single-use invitation valid for 24 hours |
| `POST /register` | `{ "invitation": "...", "username": "...", "password": "..." }`; creates a normal account; then log in |
| `GET /users` | Administrator only; account IDs, usernames, active/admin flags; no hashes |
| `POST /users/{user_id}/revoke` | Administrator only; disable user and terminate all sessions; self-disable blocked |
| `GET /decks` | Authenticated browsing; returns `decks`, up to 50 records |
| `GET /decks/{id}` | Latest `publication` with deck, owner, colors and revision |
| `GET /decks/{id}/revisions/{n}` | Immutable historical revision of an accessible publication |
| `POST /decks` | `{ "deck": <Deck.to_dict()>, "color_identity": ["U"] }`; returns server `deck_id`, `revision: 1` |
| `PUT /decks/{id}` | Same body plus `expected_revision`; owner/admin only; append revision |
| `DELETE /decks/{id}` | `{ "expected_revision": 2 }`; owner/admin only; unpublish, retaining history |

Browse filters are `query` (name/description substring), `commander` (name
substring), `owner` (exact username), `tag` (exact deck tag/theme), `color` (exact
identity such as `WU`, or `C` for colorless), and `offset` (0–100000). Text matching
is case-insensitive. Colors are normalized into WUBRG order. Each response includes
the complete deck preview payload, selected printing coordinates, categories,
commander IDs, owner, colors, `revision` and `latest_revision`. Use offsets in
increments of 50 to browse more results. Each request sees current data; clients
should deduplicate IDs if publications change during pagination.

Server IDs and deck IDs are UUIDs. Clients must use `(server_id, deck_id)` as the
remote identity, rather than treating a remote deck ID as their local deck ID.
Every explicit create publishes independently; retain the returned ID to update
the same publication. Concurrent/stale changes return 409. Unpublished decks and
decks belonging to disabled users return 404 to readers, including historical
revisions. The owner or administrator can republish by PUT using the latest
revision. The original owner stays the owner when an administrator updates it.
Clients can compare the latest revision to a cached revision before offering an
update; automatic desktop polling and offline caches belong to stage 2.

Shareable fields include names, descriptions, format, commanders, categories,
tags, card names/quantities/sections, notes and printing/oracle identifiers.
Unknown fields are dropped. Personal Printed/Pending/No Tag state, ownership
counts, `do_not_print`, printing settings, playtest notes, local image asset paths,
external artwork URLs and custom artwork overrides are excluded. Selected standard
printings survive through card ID, set and collector number. Sharing custom image
assets is unsupported in this stage. The server neither downloads card images
nor reads paths or URLs found in decks.

The URL namespace versions the protocol independently of `APP_VERSION`.
Unsupported namespaces return 426 with the supported version. Incompatible database
schemas prevent startup rather than modifying stored data.

## Operations and recovery

Stop the server with Ctrl+C before copying the **entire data directory** for a
consistent backup. Keep backups private. Upgrades replace application code and
leave that directory intact. This stage provides no uninstall/delete-data command
or automatic migration. Never delete it as part of repair/reinstallation.

If binding fails, check the chosen IP, firewall and port. If storage is unavailable,
check service-account permissions and free space. For an unreadable/incompatible
database, stop the service, preserve the original directory, then restore a known
good backup to a separate directory and explicitly start against that directory.
If initialization was interrupted, preserve its directory and initialize a new
directory. A forgotten administrator password currently requires private operator
recovery from backup; there is no HTTP password reset or public account recovery.
Password rotation, invitation listing/revocation, account reactivation, additional
administrator management and automated backup/service repair UI remain future work.

API responses never echo passwords, bearer tokens (except successful login),
invitation secrets (except creation), SQL details or tracebacks. The server has no
request-body/access logging. Operators must configure their proxy and service
logging to redact Authorization and avoid recording request bodies. No data
retention quota or automatic history pruning is implemented; monitor disk usage
for your friend group. This stage is not a centralized public service.

## Validation

`mtg_core/tests/test_library_server.py` adds in-process WSGI and storage tests for
permission checks, revisions/conflicts, filtering, request validation, private-data
projection, invitations, revocation, expiry, persistence and independent servers.
The existing Windows Python 3.12/3.13 workflow collects these tests and installs
the optional server dependency. No tests or builds were executed locally for this
implementation, per the requested execution policy. Live LAN/tunnel deployment,
desktop integration and full acceptance testing remain for subsequent stages.
