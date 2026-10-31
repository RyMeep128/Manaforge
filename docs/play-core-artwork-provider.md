# Offline Core artwork provider

Status: G1/P3 foundation at 0.5.89-alpha.1; production launcher/scene mounting and
general face contracts remain open. No live-engine, G0 or G1 acceptance claim.

`mtg_play.artwork_bundle.export_artwork_bundle` prepares an ephemeral launch
sidecar from the existing Core catalog/cache. Its caller must supply only
viewer-permitted printing IDs, on a worker, and own the private output directory.
Do not supply all players' deck membership. Persistent decks remain native
DeckDocuments; no deck format or Python per-action relay is introduced.

The exporter accepts 1–256 unique IDs and uses only the exact selected printing.
Missing metadata/artwork and unsupported faces have explicit unavailable codes;
cached alternatives are never substituted and nothing is downloaded. Standard,
normal, single-face printings are supported initially. Specialized layouts remain
available in the public fixture renderer, but are not yet supported by this live
provider contract. Existing artwork decoding is shared with the fixture exporter.

Each manifest version 1 records session/viewer context, trusted Core face metadata,
dimensions, RGBA8 bottom-left pixels and SHA-256 digests. Content-addressed raw
files have bounded dimensions/bytes; the manifest is published last in a new
directory. A failed export can leave an incomplete owned directory for host
cleanup. No source cache files, preferences or decks are modified. The manifest
digest must arrive via trusted launcher bootstrap, independently of untrusted
peer messages. The digest verifies integrity; it is not seat authentication.

`CoreArtworkBundle.OpenAsync` validates that pin, exact schema, viewer context,
safe filenames and bounded declared assets on a worker. It loads only metadata.
`LoadAsync` lazily reads and verifies raw pixels for a surface-issued request and
passes them to PreparedCardArtwork. The existing artwork coordinator and mailbox
enforce current epoch/revision admission; Unity uploads textures on its UI thread.
Errors expose a fixed code rather than private paths. Cancellation is checked
during reads and temporary byte arrays are cleared after use.

The provider rejects filesystem reparse points and path traversal. It expects a
launcher-owned private directory; it does not provide an OS sandbox against
hostile filesystem replacement races. The host must revoke the viewer, stop jobs,
await their Completion away from the UI thread, dispose the metadata provider,
then delete its owned sidecar. Provider disposal alone does not cancel active
reads or delete files. Deadlines/global retirement policy remain host work.

For public diagnostic cards only, `tools/prepare_play_artwork_bundle.py` accepts
`--session`, `--viewer`, repeated `--printing-id` or `--name`, and a new `--output`
directory under Unity Artifacts. It prints counts and the manifest pin. Exact-name
lookup may select an uncached printing; that is reported unavailable.

Focused local evidence: 20 Python checks, 321 Unity EditMode checks including Java
protocol preflight, and 32 graphics-enabled PlayMode checks with no skips. These
cover existing fixture conversion, exact pixels and hashing, missing/unsupported
artwork, budgets, malformed IDs, pin/schema/context rejection, traversal, corrupted
pixels, cancellation/disposal, and an owned job-to-renderer upload. The optional
MANAFORGE_CORE_ARTWORK_PROOF and MANAFORGE_CORE_ARTWORK_PROOF_PIN environment
variables let that upload test consume a Python-produced diagnostic sidecar;
ordinary CI uses its synthetic sidecar without external artwork dependencies.
Both the synthetic and Python-produced sidecar graphics runs passed all 32 checks
locally. Installed-cache Grizzly Bears/Pacifism name lookups reported their exact
selected printings unavailable, without fallback or downloads.
No full application suite ran. CI review remains every third implementation
commit, next at 0.5.90. Public fixture UI is unchanged; no owner UI review needed.

The subsequent [presentation pump](play-presentation-pump.md) provides bounded
per-update snapshot, texture-upload and artwork-admission coordination. The
product host still needs private bootstrap and actual scene mounting.
