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

Specialized cards use complete authentic images in both compact and full views,
with no ordinary-frame overlays, art-only crop or fabricated P/T/rules boxes.
Full inspection preserves source-image aspect ratio; compact thumbnails letterbox
inside the existing board slot. The Inspect dropdown provides access to entries
beyond the first 20 grid slots. Printed loyalty, chapter, defense, token and
emblem information is preserved in the source image, not presented as mutable
current engine state. Catalog scanning orientation is retained; dedicated Battle/
plane orientation and dynamic frame profiles remain future work.

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
& "$project/Builds/Windows/ManaforgePlay.exe" -manaforgeArtworkFixture "$project/Artifacts/LayoutGallery-20261030-complete"
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
