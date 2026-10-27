# Self-hosted Deck Library — stages 1–4

Manaforge stays local-first. Installing or launching the desktop app does not
start a server, connect to a library, create an online account, open router ports,
or install Cloudflare. There are no default library connections or developer
server addresses. Anyone can operate an independent library with its own users,
database, server UUID, and published deck IDs.

The server supplies a standalone JSON API, persistent SQLite storage,
invitation-only accounts, and revisioned publications. The desktop now supplies
Browse Online, multiple saved connections, account sign-in/invitation redemption,
deck searching, previews, independent local copies and explicit publishing from
the unified deck editor, plus read-only offline follows with staged revision updates.
Installation/Settings hosting controls remain planned. Those features are not
exposed as partially working desktop actions.

## Browse Online

Open **Browse Online** from the home page, then **Add library…**. Enter the HTTPS
origin supplied by your friend or your own server, and your account credentials.
For a new account, also enter the single-use invitation from its administrator.
For a trusted LAN, explicitly enable LAN HTTP and use a private IP address; HTTP
to hostnames or public IPs is rejected. Server URLs cannot include credentials,
paths, query strings or fragments. Redirects are rejected, including redirects
to another hostname; provide the final library origin directly.

The first sign-in pins the server UUID. Reconnecting to an address that now serves
a different UUID stops before sending credentials. Remove that connection and
explicitly add the new library if the change was intentional. Certificate
validation stays enabled for HTTPS. The client ignores environment HTTP proxies
and uses a bounded response size and network timeouts.

Saved connections contain the URL, library name, UUID and LAN HTTP preference.
Passwords are never saved. Each library's bearer session lives in memory and is
not shared with other connections. Restarting Manaforge requires signing in again;
secure OS-backed persistent credential storage remains future work. Selecting a
saved library or opening Browse Online never automatically contacts it. Use
**Sign in / Reconnect…**, then **Search / Refresh**. Errors and connection status
appear beside the connection controls. An invalid/expired session asks you to
sign in again. **Disconnect** revokes the server session when reachable and clears
it locally even when offline. **Remove** forgets just that connection and its
in-memory search results, leaving other libraries and all saved local decks intact.

Search by name/description, commander, owner, deck tag/theme and exact color
identity. Search results arrive in pages of 50; **Load more** continues the last
submitted search. Selecting a result previews its owner/revision, description,
commander, categories, tags, quantities, card notes and selected printing IDs.
Commander artwork uses the existing thumbnail component against the local card
image cache only; missing images show no artwork. This page makes no artwork
provider requests. Search, sign-in, disconnect and disk copying use the existing
background job queue and show a progress indicator.

**Copy to My Decks** saves the selected preview as a native Manaforge deck with a
new local UUID and source attribution. Open it through **Deck Editor → Projects**.
The copy is independently editable and available after restart while offline.
It includes the previewed revision; copying again deliberately makes another
independent deck. It receives no future updates. Local print/ownership state,
custom artwork paths, project settings and unknown remote extras are excluded.
Removing the server connection cannot delete or modify these decks. If a search
fails, the previously displayed results remain labeled as an earlier snapshot;
you can still copy one while disconnected. Search snapshots are only kept for the
current application session; save a local copy or follow the deck for offline use after restart.

## Publish, update and unpublish

In the unified Manaforge application, open a deck in Deck Editor and choose
**More → Publish to Library…**. Manaforge saves the deck locally, freezes a shared
snapshot and opens its publishing panel in Browse Online. Select a destination
library above the panel and sign in if needed. Review the snapshot name and color
identity, then choose **Publish snapshot**. Color identity is suggested from local
card facts and can be corrected before publishing. Opening the panel never uploads
anything. The standalone editor launcher keeps this action disabled; use the
unified application for online publishing.

The first publish creates a new server publication. Subsequent explicit publishes
from the same local deck to the same library update that publication with a new
revision. A separate library receives its own publication only when you select it
and publish. Later local edits are never automatically uploaded. Choose Publish
to Library again from the editor to prepare a fresh snapshot. A copied deck has
a new local ID and publishes independently of its source.

The panel displays the last acknowledged server deck ID, revision and published
state. **Unpublish** hides that publication from readers but retains server history
and your local deck. Publishing again uses the same server ID and a new revision.
The server enforces owner/administrator permissions on every modification; signing
in as another normal user cannot update someone else's publication. General
administrator deck management remains available through the API; the desktop panel
manages publications linked to your local decks.

A durable local journal records an operation before uploading. If an upload or
its response is interrupted, **Retry pending publish/unpublish** retries that same
operation and original snapshot, including its original colors. Edits made after
the pending snapshot are not part of the retry. Once recovered, prepare another
snapshot to publish the newer edits. The journal contains only shared deck fields
and account/server identifiers, never passwords, bearer tokens or print status.
The server atomically stores an operation receipt with the publication; repeated
requests return the original result without creating duplicate decks/revisions.
Pending retries require the same user account that started them. This remains true
after an application/server restart or reconnect.

If another client published a newer revision, the update stops with a conflict.
Choose **Review latest publication** to load the remote deck into the preview.
Reading it does not change your local deck or publishing base. If you intend your
next explicit publication to replace that remote content, choose **Use reviewed
revision as the next publish base**, then separately publish or unpublish. This
clears the conflicting pending operation and leaves the local deck and prepared
snapshot unchanged. A further remote change still causes another conflict. An
unavailable/unpublished source may not be reviewable; retry/reconnect diagnostics
leave the local deck and journal intact.

Publication links are keyed by `(server_id, local_deck_id)` and survive removing
and re-adding a connection, preventing accidental duplicate publication after a
reconnect. Removing a connection does not unpublish its decks. Application updates
leave the journal in the application data directory alongside saved connections.
Published deck notes, descriptions and tags are intentionally shared; private
project extras, ownership counts and personal print statuses are excluded.

The desktop requires the server's `publication_operations` capability and a
verified account ID from login. Upgrade an older library server and sign in again
before publishing; browsing older API-v1 servers remains supported. Publication
receipts report the originally completed operation, so review the latest deck if
another client may have changed it since then.

## Architecture and remaining stages

`mtg_core.library.payload` projects the existing `mtg_core.decks.Deck` model into
an allowlist of shareable fields. `store` owns persistence and authorization;
`api` exposes a versioned WSGI application; `__main__` starts a separate Waitress
process. Nothing imports the desktop application or exposes desktop commands.
The optional Waitress dependency is separate from desktop requirements.

Reuse points for follow-up work:

1. Credential management: add secure optional credential storage using the
   operating system credential store rather than saving bearer tokens in the
   connections database. Browse Online and editor publishing already reuse the
   separate client, connection metadata, `mtg_ui.jobs.JobQueue`, Home registry,
   existing thumbnail/deck components and per-library publication journal.
2. Hosting UI: add a disabled-by-default **Host a Manaforge Deck Library** section
   to `mtg_ui.data_management.DataManagementDialog` (current first-run setup), and
   shared Settings controls. Configure storage, administrator, LAN/tunnel,
   background startup, health checks and repair without overwriting databases.
   Joining belongs exclusively in Browse Online. Skipping hosting must skip all
   server dependencies/configuration. Bundle/service lifecycle work remains here.

## Followed decks and offline updates

Select a shared search result and choose **Follow Deck**. Manaforge explicitly
downloads the latest publication and caches a native `DeckDocument` in its local
connections database. **Followed decks (offline)** shows cached decks from every
library, with source-library labels, accepted revision, availability state and
update badges. The preview is read-only; follows are kept outside the editable
deck directory and cannot accidentally open as editor projects. They remain
viewable after restart without signing in or connecting to any server.

Each follow uses `(server_id, deck_id)` as its source key, plus a separate stable
local UUID and accepted revision. Different libraries can use identical deck IDs
without colliding. Removing a connection retains its offline follows, recovery
history and independently editable deck copies. Re-add/sign in to that library
to check for updates again. **Copy to My Decks** works from the accepted offline
cache even when its connection has been removed; the new editable copy receives
its own UUID and source attribution and never synchronizes automatically.

**Check selected library for updates** checks active subscriptions for the library
selected in the connection selector. New revisions are downloaded to a staged
slot and trigger an update count/notification. The accepted cache is unchanged.
**Review cached update** opens the downloaded revision in the preview. Then
**Accept reviewed update** atomically replaces the accepted cache with exactly
the reviewed revision. If a check staged a different update in the meantime,
acceptance stops and asks for another review. Reviewing and accepting staged
content require no network connection; it was already downloaded while authorized.

Automatic checks default **off**. Optionally enable **Check this library every
5 minutes while signed in** for an individual library. The app checks due libraries
using its shared background queue, with roughly 30-second scheduling granularity,
and shows notifications in Manaforge's status bar. It never applies updates.
These checks only run while that library has an explicitly established in-memory
session; saved preferences do not reconnect or authenticate on startup. Other
libraries keep their own preference and schedule. **Stop following (keep offline
copy)** disables future checks for that deck and retains the accepted read-only
cache. Following it again stages newer content without replacing the old cache.

An offline, deleted, unpublished or inaccessible source changes the availability
message while retaining the accepted cache and any staged revision. Expired
sessions require signing in again. The client verifies server identity, rejects
revision rollback, and reports content changed without a new revision. It does
not replace previously staged data with inconsistent or older content. An owner
unpublishing a deck cannot retract copies clients already downloaded.

Update acceptance preserves local document settings and existing per-card print
fields/extra metadata, including future print-status fields. Existing cards are
matched by stable entry ID and card identity; unambiguous regenerated IDs can also
match by card/section. New cards use current local model defaults; this stage does
not add Printed/Pending/No Tag values or couple to the planned print-status UI.
Removed/changed-card state stays in the previous accepted recovery snapshot.
Five prior accepted revisions are retained locally. A content fingerprint detects
local decklist edits and refuses to overwrite them; make an independent copy
before resolving such a change. Failed/interrupted checks and failed SQLite
transactions leave the accepted document and its print data intact.

Subscription, staged-update, history and preference tables share the private
application connection database. They store native deck JSON, not another deck
format, and contain no passwords or bearer tokens. Back up this database while
Manaforge is closed to preserve offline subscriptions, publication links and
recovery snapshots across repairs. There is no automatic cache deletion on
upgrade, connection removal or repair. Recovery snapshots currently have no
separate restore UI.

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
| `POST /login` | `{ "username": "...", "password": "..." }`; returns `token`, `user_id`, `expires_in` |
| `POST /logout` | Revoke current session immediately |
| `POST /invitations` | Administrator only; returns a single-use invitation valid for 24 hours |
| `POST /register` | `{ "invitation": "...", "username": "...", "password": "..." }`; creates a normal account; then log in |
| `GET /users` | Administrator only; account IDs, usernames, active/admin flags; no hashes |
| `POST /users/{user_id}/revoke` | Administrator only; disable user and terminate all sessions; self-disable blocked |
| `GET /decks` | Authenticated browsing; returns `decks`, up to 50 records |
| `GET /decks/{id}` | Latest `publication` with deck, owner, colors and revision |
| `GET /decks/{id}/revisions/{n}` | Immutable historical revision of an accessible publication |
| `POST /decks` | `{ "deck": <Deck.to_dict()>, "color_identity": ["U"], "operation_id": "<UUID>" }`; returns server `deck_id`, `revision: 1` |
| `PUT /decks/{id}` | Same body plus `expected_revision`; owner/admin only; append revision |
| `DELETE /decks/{id}` | `{ "expected_revision": 2 }`; owner/admin only; unpublish, retaining history |

`GET /info` advertises `capabilities: ["publication_operations"]`. Include a fresh
canonical UUID `operation_id` on POST/PUT/DELETE publication changes, persist the
exact request before sending, and reuse that operation ID and content when retrying.
Receipts are scoped to the authenticated user. Reusing an operation ID for different
content returns 409. Update/unpublish still require `expected_revision` and
ownership. PUT/DELETE return `deck_id` and `revision` too. Older API clients may
omit operation IDs, but do not then have a safe automatic retry guarantee.

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
Desktop following compares the latest revision to its accepted/staged cache;
only explicit acceptance changes the accepted offline document.

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
leave that directory intact. Startup adds an operation-receipt table to existing
schema-v1 databases without replacing data, identity or history. There is no
uninstall/delete-data command or destructive migration. Never delete it as part of
repair/reinstallation. Back up before upgrading.

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
`mtg_core/tests/test_library_client.py` covers transport constraints, identity
pinning, session separation, untrusted responses and local copy isolation.
It also bridges the client to the actual WSGI API to exercise publication and
recovery after a response is lost following a server commit, without real networking.
`mtg_core/tests/test_library_publishing.py` covers durable pending snapshots,
separate library links, same-account retry protection and explicit conflict review.
Server tests cover idempotent create/update/unpublish, revocation and the additive
schema upgrade.
`mtg_core/tests/test_library_following.py` covers native offline documents, staged
updates, private print metadata, failed transactions, revision rollback, local-edit
guards, history bounds, source namespaces, stopped follows and cancellation.
`integration_tests/test_library_workspace.py` covers opt-in startup, background
browsing, plain-text previews, copying, separate connection snapshots and failure
preservation, plus explicit publication/conflict review, offline restart, follow
review/accept and connection-free copying with fake clients. The
homepage tests cover editor-to-library routing without automatic upload. The existing Windows Python 3.12/3.13 workflow
collects these tests and installs the optional server dependency. No tests or
builds were executed locally, per the requested execution policy. Live LAN/tunnel
deployment and full story acceptance testing remain for subsequent stages.
