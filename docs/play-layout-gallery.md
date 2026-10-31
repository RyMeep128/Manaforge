# Specialized-layout renderer gallery

Owner scope expansion, October 30, 2026: include planeswalkers, sagas, battles,
tokens and other unusual layouts in the Unity fixture, and inspect the provided
Downloads assets for implementation help. This extends visual coverage; it does
not bypass G0/G1 or implement game rules, ability choices or live-engine play.

The local gallery contains 25 public face entries with exact printing identities:
planeswalker, saga, Battle front/back, Treasure and Soldier tokens, emblem,
transforming creature front/back, modal DFC front/back, split, Adventure, level-up,
Class, Case, Room, prototype, mutate, meld parts/result, dungeon, plane, scheme and
Vanguard. These are representative cases, not coverage of every Magic printing.

The updated version-2 gallery now uses actual compact battlefield profiles for
recognized layouts: cropped illustrations, independent framed names, kind labels
and supplied P/T, loyalty or defense badges. Split cards use two art panes from
one borrowed printing texture. Room/Battle/plane profiles rotate their artwork and
full inspection for reading. The ordinary-card renderer and unknown-layout image
fallback remain available. Full specialized inspection still uses the authentic
printing, so printed ability rows and chapter text are preserved rather than
pretended to be dynamic components.

Loyalty and defense in this gallery are explicitly printed-reference mock values;
only supplied values render. Saga chapter/lore progress is not inferred from
rules text. Future live projections must supply engine-authoritative current
values. Per-family crops are initial geometry profiles reviewed on these gallery
printings, not guaranteed art-focus coordinates for every alternate printing.

Normal-layout planeswalkers and auxiliary types are now conservatively excluded
from the ordinary 2015-frame reconstruction policy. No card text is interpreted
as a rule. Unknown/special presentations retain authentic-image fallback. Existing
saved diagnostic bundles retain their own recorded compatibility flags; regenerate
them to use the revised collector classification.

Preparation uses the existing Core catalog/image cache. Four missing selected
DFC images were populated through the existing Core artwork service, separately
from the offline exporter. The final export has 25 shared textures, 29,219,840 raw
RGBA bytes and no missing-art entries. The exporter itself still forbids network
access. Selected front/back identities are preserved without front substitution.
Fixture capacity is now 32 entries; the 48-asset, 64-MiB and 1-MiB-manifest bounds
remain enforced on both export and import. There is no deck read or second model.

Reproduce after the necessary public artwork is installed:

```powershell
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe tools/prepare_play_artwork_fixture.py --preset layouts --output Mtg_Projects/mtg_play_unity/Artifacts/LayoutGallery-new
./tools/unity-play.ps1 -Mode Build
./tools/unity-play.ps1 -Mode ArtworkSmoke -FixtureDirectory Mtg_Projects/mtg_play_unity/Artifacts/LayoutGallery-new -FixtureCount 20
```

For manual review from the repository folder:

```powershell
$project = (Resolve-Path "Mtg_Projects/mtg_play_unity").Path
& "$project/Builds/Windows/ManaforgePlay.exe" -manaforgeArtworkFixture "$project/Artifacts/CompactLayoutGallery-20261030"
```

Use Inspect to review every face, particularly planeswalker loyalty boxes, Saga
chapters, both Battle faces, tokens, emblem, split/Adventure and the auxiliary
cards. Try 70 objects to include every entry in the grid. Confirm full inspection
retains the source frame and footer. This gallery is printed mock data, not a
match or evidence of legal interactions. Owner visual review remains required.

The provided Wizards folder has useful supporting parts; see the
[asset inventory](play-provided-art-assets.md#specialized-card-parts--october-30-2026).
No provided runtime/code/bundle is imported into the tracked project in this
increment. Curating its textures, SDF fonts, layout transforms and materials into
Manaforge-owned components is a separate step from this safe display fallback.


Validation passed: 48 focused Python catalog/export checks, 246 Unity EditMode
checks, four PlayMode checks, Ruff, the Windows build and the 20-object packaged
gallery smoke. The capture was inspected for complete specialized printings and
readable full-card inspection. No full application suite ran. Owner visual review
is pending. CI checking is due after the next commit under the third-commit
cadence; no new CI pass is claimed for this increment.


## Compact-layout follow-up — October 30, 2026

The owner correctly identified the first gallery as printing thumbnails rather
than mini cards. The v2 fixture now carries printing layout plus nullable printed
loyalty/defense, while v1 remains loadable with its prior fallback. This changes
only the local diagnostic fixture, not the public Java/C# game protocol. Original
v1 bundles must be regenerated to opt into the explicit compact metadata.

Reproduce with --preset layouts as above, using a fresh output directory. The
current local review bundle is `Artifacts/CompactLayoutGallery-20261030` (25 faces,
25 shared textures). Full inspection and minis remain separate modes; names and
numeric badges are independent of artwork. Unknown fields do not receive default
values. Missing/faulted artwork and viewer concealment retain existing behavior.


Compact follow-up validation passed: 268 focused Unity EditMode checks, five
PlayMode checks, 50 focused Python catalog/export checks, Ruff, the Windows build
and the 20-object packaged compact-gallery smoke. Captures were inspected for
cropped minis, nameplates, badge values and split panes; owner visual approval is
still pending. No full application suite ran. CI checking is due after two more
commits under the owner's third-commit cadence; no new CI pass is claimed here.
