# Play launch manifest — P1.3 foundation

Status: export and fixture boundary implemented; process delivery and engine
resolution remain pending. See the [migration roadmap](play-unity-java-roadmap.md).

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
and rejects nine malformed shapes. The Java reader is test-only schema validation,
not an authenticated production gateway parser. CI checks fixture/model drift;
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
