# Owner-provided Wizards asset inventory

On October 30, 2026 the owner supplied the local folder
`C:/Users/ryanm/Downloads/Assets from Wizards, given with permission` and stated
permission to use its assets. The supplied folder remains unchanged and external
to the repository. This records that provenance, not independent verification of
the grant's wording. No asset bundle, DLL, configuration, audio or extracted image
from that folder is committed in this increment.

Read-only inventory found 28,617 files (about 13.86 GiB), mainly compiled Unity
`.mtga` bundles, plus an indexed JSON manifest. Relevant entries include card
base, title-bar, type-line, textbox, P/T, mana-symbol and field-font parts. These
are strong candidates for replacing prototype components, rather than importing
the supplied runtime into Manaforge.

Selective local decoding confirmed:

- `BELEREN2016-BOLD` in the Fonts bundle, alongside Minion and other fonts.
- `CDC_PowerToughness_Default_Green`, `_Black` and `_Red` textures (128 by 64).
  The green P/T texture was decoded and visually inspected as a beveled inset.
- `SDF_Icons_ManaCost_Symbols`, backs, SDF variants and alternate symbol sheets.
- Card base/title-bar/type-line component entries in the source manifest;
  their complete standard texture/material dependencies are not yet resolved.

Inspection used UnityPy 1.25.4 installed only under ignored Artifacts, not in the
application dependencies. Some bundles suppress their Unity version; decoding
used an explicit 6000.3.14f1 fallback taken from the accompanying serialized player
files. This is a parsing assumption, not proof that every bundle uses that version.
Local decoded samples and inventory live under
`Mtg_Projects/mtg_play_unity/Artifacts/AssetInspection/` and are not tracked.

Next integration should curate ordinary frames, compact/full nameplates, a P/T
box, mana sprites and the required font resources, preserving source bundle/path
IDs and hashes. Rebuild Manaforge-owned components around those resources; avoid
a dependency on supplied gameplay code or shaders that have not been adapted to
our URP/UI Toolkit pipeline. SDF atlases require glyph metadata/material handling,
not just importing their PNGs. Keep XMage, native decks, viewer privacy and the
public game protocol unchanged. A fresh owner visual review will be required
when the imported components are wired into the fixture.
