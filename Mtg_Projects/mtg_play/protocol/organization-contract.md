# Organization contract v1 (CT-09A)

Standalone contract work only. No organization packets are sent, routed, or admitted
by ordinary gameplay connections. The legacy envelope, authentication proof/hello,
and receive dispatch remain unchanged. Never probe a strict legacy receiver with a
capability packet; the future authenticated coordinator must explicitly select the
organization path. This is neither peer-to-peer discovery nor multiplayer delivery.

`organization-v1.schema.json` is the reviewed source. Generated organization DTOs
and embedded schema are separate from existing gameplay contracts. Do not hand-edit
generated files. Use `tools/generate_play_models.py` and its `--check` mode.
The fixture generator similarly supports `--check`; its public synthetic context
is test data, not a wire format for host identities.

## Shapes and limits

The standalone envelope has exactly wire_version=1, organization_version=1,
message_type, message_id, and body. Message families are organization_capabilities,
organization_command, organization_receipt, and organization_snapshot. Capabilities
list supported versions; version 1 is selected only with caller-supplied authenticated
context and mutual support. A missing supported version disables organization.

Commands contain match epoch, command ID, expected organization revision, basis
revision, and operation. There is no editable actor/owner field. Operation kind is
create, rename, delete, position, reorder, or move. The fixed operation shape always
contains group_id, name, x, y, index, and members; unused scalar fields are null and
unused member lists empty. Null move destination means root. Reorder addresses the
final group order; move indices address the destination after selection removal.
Move lists contain viewer handles, never host incarnation IDs.

Receipts contain match/command IDs, outcome, both resulting revisions, and reason_code.
Applied receipts require null reason; rejected receipts require an allowlisted code.
Snapshots contain match/viewer context, both revisions, ordered seats/groups/roots,
and mappings from viewer handles to current admitted object references and seats.
They never serialize host reducer state directly or include unadmitted-member counts.

Positions use integers 0..1,000,000, converted to normalized reducer coordinates.
Do not relax the existing integer-only gameplay parser. Revisions are nonnegative
signed 64-bit integers. IDs are 1..128 ASCII characters from letters, digits, _ . : -.
Names allow 1..64 Unicode scalar values, reject controls and whitespace-only labels.
Manual labels are not keys or automatically derived from concealed card identities.

Maximum encoded organization size is 256 KiB UTF-8, with eight seats, 32 groups per
seat, 1,024 total projected members, and 128 members per command selection. Encoded
size takes precedence when individual count maxima cannot fit together. No truncation
is allowed. Existing strict JSON depth, duplicate-key, Unicode and integer rules apply.

## Evidence and integration gates

The shared corpus records schema_valid separately from valid: JSON Schema checks
the parsed structure, while strict Java/C# readers additionally reject duplicate
keys, fractional integer spelling, invalid Unicode, over-budget bytes, and wrong
viewer/basis references. Schema conformance alone is not admission or authentication.

Java and C# validators/codecs and cross-language contextual checks follow in the
second review step. Hosted cross-language evidence is required before CT-09A is
accepted. A local Unity build is attempted after C# changes; missing licensing or
skipped hosted Unity checks are not passing evidence. Native identity acceptance,
authenticated viewer coordination, deduplication, and live integration remain gates
before any shared organization can be exposed to players.
