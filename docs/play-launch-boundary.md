# Play launch manifest — P1.3 foundation

Status: export, shared fixtures and Java runtime input validation implemented;
process delivery and engine resolution remain pending. See the [migration roadmap](play-unity-java-roadmap.md).

`mtg_play.launch_manifest.export_launch_manifest` accepts native `DeckDocument`s
keyed by seat ID, existing `GameSetup`, application version and optional deck-owner
provenance. It returns immutable UTF-8 bytes. It starts no engine, writes no file
and changes no saved deck. The existing artifact manifest supplies the runtime pin.

```python
payload = export_launch_manifest(
    setup,
    {"human": human_document, "opponent": opponent_document},
    manaforge_version=APP_VERSION,
    deck_owners={"opponent": borrowed_deck_owner_id},
)
```

Only the **trusted gateway owner** receives this all-decks payload. Never send it
to Unity, remote seats, diagnostics or screenshot artifacts. Launch DTOs are
generated for Java only. Owner IDs are provenance, not seat credentials or required
accounts. `manifest_id` is an ephemeral identifier, not authentication.

## Native projection and validation

The nested document retains native schema/field names: deck ID/name/format,
entry IDs/names/quantities/sections, selected `card_id`, Oracle IDs, set/collector
identifiers, owned counts, front/back asset references, `commander_entry_ids` and
the existing `companion_entry_id` metadata key. Source edits cannot change exported
bytes. `DeckDocument.from_dict` can inspect the minimal projection with ordinary
defaults; never save it over the original document.

Considering, excluded, display-only commander and zero-quantity entries are
omitted consistently with the adapter. Notes, categories, tags, print settings,
preferences and unrelated extras are omitted. Custom artwork override rendering
is not implemented here; original data remains intact. Asset references are opaque
strings and are never opened or fetched.

Structural checks reuse `deck_document_issues`, then validate seat/deck/owner
mapping, native schema, identity/reference consistency and scalar types. Missing
printings remain null. Unsupported sections and malformed inputs fail with codes;
exceptions do not include card/deck contents. No rule, canonical-name or engine
printing resolution is performed. Companion quantities and card arrangements are
preserved for XMage to decide, rather than normalized into presumed legality.

The 1 MiB payload limit, 4096 exported entries per deck, 4096-character text limit
and signed-64-bit integers are transport bounds, not Magic rules. No five-seat
protocol maximum is imposed. Export acceptance does not certify engine support
for every format/controller/seat arrangement.

## Evidence and reproduction

`launch-manifest-v1.schema.json` is distinct from game protocol 1 and native deck
schema 1. Synthetic fixtures are produced from native documents without user data.
Three positives cover human/AI Freeform, human/AI Commander with commander/partner
or background and companion metadata, and five-seat Commander setup. These are
serialization examples, not played games or card-eligibility claims.

```powershell
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe Mtg_Projects/mtg_play/tests/generate_launch_fixtures.py --check
python tools/generate_play_models.py --check
python tools/check_play_java_protocol.py
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe -m pytest Mtg_Projects/mtg_play/tests/test_launch_manifest.py -q
```

Local evidence: 29 focused Python launch tests; Java round-trips three positives
and rejects nine malformed shapes. The initial Java fixture consumer is test-only schema validation. The runtime
reader below adds input checks but does not authenticate a gateway process. CI checks fixture/model drift;
its status is reviewed every third commit under the owner's cadence.

## Remaining acceptance

Java must resolve cards, canonical-name/catalog context where needed, exact
printings, format and commander/companion rules using XMage. Stored names/IDs are
preserved, not certified as engine-resolvable. Never substitute unsupported cards.

The [P1.4 lifecycle foundation](play-launch-lifecycle.md) adds owned-root cleanup,
cancellation and retry blocking. Private delivery, OS containment and orphan recovery
remain pending. P4 must connect saved-deck selection
and owned processes. This increment writes no temporary manifest, changes no Qt
launcher, and completes neither G0/G1 nor human-versus-AI acceptance.


## Java runtime launch reader (0.5.123)

LaunchManifestReader.parse accepts the existing versioned native projection and
three expected runtime pins supplied by the trusted host (engine version,
adapter version and artifact manifest SHA-256). Never derive expected pins from
the received manifest itself. Mismatches fail before a DTO is returned. This is
P1.3 launch-boundary work, not bulk P2 engine migration or P4 launch acceptance.

The reader reuses generated Java-only LaunchContracts DTOs. It validates exact
record fields/types, launch/game/native-deck versions, supported format/controller
labels, unique seat/entry IDs, positive quantities/nonnegative ownership, native
commander references and sideboard companion references. Optional printing and
asset IDs remain nullable/opaque. Entries keep their source ordering, exact
printing IDs, quantities and commander/companion metadata. No card names are
resolved, printings substituted, canonical documents saved or engine rules copied.
The returned mutable DTO belongs only to the Java gateway input owner; it is not
a public immutable GameSnapshot and must never enter a Unity/viewer channel.

WireEnvelope.parseObject factors out the existing bounded strict JSON parser;
WireEnvelope.parse still performs the unchanged envelope header checks afterward.
This avoids wrapping the private manifest in a fake public game message. UTF-8
size/depth, duplicate keys, malformed Unicode and signed-64-bit integer rules are
shared. Required text and 4096-code-point bounds mirror the Python exporter;
blank entry names remain permitted as in the source contract. Six-seat input is
tested without imposing a five-seat maximum. Schema acceptance does not establish
engine support for any seat/controller/card combination.

Errors contain fixed codes only, without input text or nested parser exceptions.
The reader performs no IO, process launch, credential issuance or network writes.
A manifest ID and deck-owner provenance still do not authenticate seat ownership.
Inherited private delivery, cancellation/deadlines and process-ready handshake
must be supplied by the launch owner in a later integration step, followed by
XMage-specific identity/card resolution. No Java gameplay gateway is claimed.

Local validation passed: 44 runtime reader checks, full focused Java protocol
preflight, launch-fixture/schema drift check and Java/C# generated-model drift
check. Coverage includes all three positive/nine negative shared launch fixtures,
unknown fields, version/pin changes, duplicate/missing references, boolean/fraction/
overflow numerics, trailing/duplicate JSON, BOM/Unicode limits, full signed-64-bit
quantities, source isolation and non-leaking errors. No engine, Unity build/UI or
full application suite ran. The normal protocol CI now compiles/runs this consumer;
status is checked at 0.5.123 without waiting for unfinished jobs.

Existing deck-preview and packaged decision-fixture visual review remains pending.
Automatic mana work remains parked and disabled. All G0/G1 and later acceptance
gates retain their previous requirements.


### Private native-deck delivery proof (0.5.124)

LaunchOwner.start_gateway now optionally accepts exported launch-manifest bytes.
It writes one bounded (1 MiB), length-prefixed frame through the owned gateway's
stdin, with startup/write deadlines, cancellation and the existing child-handle
cleanup. The mutable writer copy is cleared afterward; the caller still owns the
original immutable bytes. Legacy launches without a manifest remain supported.
Gateway delivery and client bootstrap use separate flags. Writing bytes does not
establish readiness, authenticate seats or authorize starting Unity.

The diagnostic LaunchBootstrapProbe reads this private pipe with the Java runtime
LaunchManifestReader and trusted engine/adapter/artifact pins. A public native
DeckDocument export reaches Java without putting deck contents in argv, environment,
stdout, a temporary manifest file or a viewer channel. Its temporary marker contains
only a fixed validation result. The parent bounds startup and closes/reaps its owned
Java process on EOF. This test receiver starts no XMage or Unity and has no engine
child processes; real runtime descendant cleanup and readiness remain integration
requirements. Blocking probe reads rely on the parent's deadline and cleanup.

Run `python tools/check_play_gateway_launch.py` after exporting compiled classes
with `python tools/check_play_java_protocol.py --download-gson --dummy-output
Mtg_Projects/mtg_play_unity/Artifacts/JavaDummy`. Its sanitized JSON report is under
Unity Artifacts/GatewayLaunchProof. Protocol CI now runs this proof; preview CI
includes the new focused gateway-bootstrap tests. CI is next checked at .126.

Local Java preflight and the cross-process proof passed. A focused Python run passed
91 cases and hit the existing forced-cleanup test's 50 ms deadline once; that test
passed unchanged when rerun alone. Windows virtualenv launcher wrappers also made
short child deadlines fail, so the final focused run used the direct interpreter
with the existing environment's dependencies. No full application suite ran.
No UI changed; previous owner visual reviews and G0/G1 acceptance remain pending.
Automatic mana work remains parked.


### Owned Java rejection matrix (0.5.125)

The private-launch proof now runs ten actual Java child processes: the existing
valid human/AI native-deck export plus nine invalid public fixtures. Rejections
cover malformed JSON, invalid UTF-8, BOM, duplicate keys, each of the three
independently trusted runtime pins, duplicate seats and dangling commander
references. Every rejection must exit with the fixed receiver failure status,
leave no validation marker (including partial markers), reap its owned root
without forced termination and refuse subsequent client admission. Unexpected
errors, timeouts or a mistakenly accepted manifest fail the proof.

Report version 2 records only fixed case labels/counts and public evidence;
no manifest content is included. An old report is removed before a rerun so failed
runs cannot retain stale success evidence. Protocol CI runs the matrix and uploads
this sanitized report under a commit-specific artifact name. The focused local
matrix passed all ten cases. CI remains scheduled for the .126 check rather than
waiting on .125. No runtime/UI behavior changed and no engine or client started.
These rejection checks do not implement the pending authenticated ready handshake,
engine descendant ownership or actual engine card resolution.
