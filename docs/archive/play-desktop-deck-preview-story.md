> Historical record, archived November 3, 2026. Commands, status claims, and
> acceptance notes below describe their original increment. Use the
> [documentation index](../README.md) and [current roadmap](../roadmap.md) for current guidance.

# Story: Launch Unity Play from Manaforge with Real Deck Cards

**Epic:** Manaforge Play — Unity + Java
**Milestone:** P3.5 — Desktop-to-Unity Vertical Slice
**Priority:** High — MVP integration
**Target:** Windows development build
**Placement:** After Unity card-rendering and launch foundations; before P4.1 real-engine launch integration.

## User Story

As a Manaforge user, I want to select my format and saved decks in Manaforge, click Start Play Preview, and have Unity launch with my actual cards displayed so that I can begin testing the visual experience without waiting for the complete XMage integration.

This is the first user-facing, end-to-end integration of the Manaforge desktop application and Unity.

## Current Implementation

Inspect the latest development branch before changing anything. Do not assume `main` contains the latest Play work.

Existing components to reuse include:

- `Mtg_Projects/mtg_home/launcher.py` — Play workspace entry point.
- `Mtg_Projects/mtg_play/workspace.py` — existing deck/format selection.
- `Mtg_Projects/mtg_play/lobby.py` — selected decks and seat identities.
- `Mtg_Projects/mtg_play/launch_manifest.py` — native deck launch serialization.
- `Mtg_Projects/mtg_play/launch_lifecycle.py` — owned child process lifecycle.
- `Mtg_Projects/mtg_play/viewer_bootstrap.py` — private startup foundation.
- `Mtg_Projects/mtg_play/artwork_bundle.py` — offline Core artwork export.
- `Mtg_Projects/mtg_play_unity/Assets/Manaforge/Runtime/CardView.cs` — reusable card rendering.
- `ViewerCardSurface.cs`, `CoreArtworkBundle.cs`, `ArtworkFixtureScene.cs` and the existing visual components.

Review `docs/play-unity-java-roadmap.md`, the relevant launch/artwork documents, and `AGENTS.md`.

Do not create another renderer, game-state model, deck database, or competing lifecycle system.

## Desired User Experience

1. Open Manaforge.
2. Click Play.
3. Choose Freeform or Commander.
4. Select the human deck and optional AI-opponent deck for future gameplay setup.
5. Click **Start Play Preview**.
6. Manaforge prepares a read-only preview of the selected human deck.
7. The packaged Unity player starts automatically in a separate window.
8. Unity displays a simple 1v1-oriented playmat preview containing actual cards from the selected deck.
9. The user can hover, select, and inspect cards using the existing card components.
10. Closing Unity returns the user to Manaforge with their deck selections intact.

The Unity window must explicitly indicate that this is a **Deck Preview — Not a Live Game**.

## Implementation Requirements

### 1. Connect the existing Play workspace to Unity

Reuse the current Qt deck/format lobby.

Add a **Start Play Preview** action to the development Play workspace. Do not replace or break the existing experimental Qt gameplay path.

The action must:

- Use the selected saved `DeckDocument`.
- Preserve the chosen format and exact printing identities.
- Reject missing or unreadable decks with understandable UI errors.
- Find and launch the existing packaged Windows Unity player.
- Run preparation and process monitoring without blocking Qt.
- Prevent overlapping preview launches.
- Provide a clear Close Preview or Cancel action.

Keep the installed Play release gate unchanged. This story does not authorize making Play generally available in the installer.

### 2. Implement a minimal preview handoff

Export a bounded, versioned, read-only projection of the chosen deck.

Include only information needed for preview rendering, such as:

- Deck display name and format.
- Deck entry identifiers and quantities.
- Oracle and selected printing identities.
- Safe printed display values where available.
- Verified artwork references.

Preserve the canonical DeckDocument as the source of truth. Preview data is not gameplay state.

**Do not send the all-seats launch manifest to Unity.**

Use a separate preview-only startup contract, reusing the existing bounded inherited-pipe infrastructure where applicable. Do not put private deck contents or authentication secrets in command-line arguments.

Do not fabricate engine object identities, legal actions, priority, game zones, or game results.

### 3. Display real cards in Unity

Reuse `CardView` and the existing runtime artwork, typography, mana-symbol, frame, and inspection components.

The initial Unity preview should show:

- A recognizable playmat surface.
- A visible collection of cards from the selected deck.
- A compact card presentation.
- A larger full-card inspection view.
- Actual card names, artwork, and printed data.
- Card selection by click and hover.
- Clear indication of the preview mode.

The initial visible set may be deterministic and bounded to keep performance predictable. It must be derived from the selected deck, not from hard-coded test cards.

Do not pretend these cards have been drawn or placed on a battlefield by XMage.

The layout should be reusable by the eventual gameplay scene rather than creating a disposable preview renderer.

### 4. Use existing artwork and fallback policy

Use Manaforge Core's offline cache and the existing artwork-bundle infrastructure.

Requirements:

- Preserve selected printing identity.
- Prefer a compatible cached standard presentation where supported.
- Support existing authentic-image rendering for unsupported special frames when a verified asset is available.
- Do not force full-art/showcase cards through incompatible reconstructed frames.
- If compatible artwork is unavailable, display an honest unavailable-artwork state rather than inventing art.
- Do not require internet access or initiate downloads.
- Reuse textures and limit simultaneous decoding and GPU uploads.
- Keep artwork preparation independent of the render thread.
- Clean up per-preview assets when the session ends.

This story does not require implementing every Magic frame treatment.

### 5. Own the Unity process lifecycle

Extend or reuse the existing launch ownership infrastructure to support a **preview-only Unity child** without pretending a Java gateway is running.

Requirements:

- Launch an owned Unity child process without a shell.
- Do not require Java/XMage for this preview.
- Do not require Unity Editor to launch the packaged player.
- Detect missing builds, startup failure and unexpected exit.
- Keep Manaforge responsive while Unity runs.
- Clean up owned temporary preview files and textures.
- Preserve user decks, artwork caches and preferences.
- Avoid terminating unrelated Unity processes.
- Handle cancellation, repeated launches and application shutdown.
- Show a useful error when cleanup cannot be confirmed.

Do not bypass the existing gateway and authenticated-session architecture for future real gameplay. Preview mode must remain explicitly separate.

### 6. Preserve the future gameplay architecture

The final implementation must continue to support:

`Manaforge Qt → launch preparation → Unity → Java gateway → XMage`

For this milestone, only the first three elements need to operate together.

The preview must be replaceable by authoritative viewer-filtered snapshots later, without rewriting `CardView` or the desktop launch integration.

Avoid new Python-to-Unity per-frame messaging, direct Unity database access, or XMage logic in C#.

## Acceptance Criteria

- [ ] The development Play workspace exposes Start Play Preview.
- [ ] A saved deck and format can be selected using the existing Manaforge UI.
- [ ] Clicking Start Play Preview launches the packaged Unity player without manually opening Unity Editor or running a terminal command.
- [ ] Unity visibly displays cards belonging to the selected deck, using correct card names and printing identities.
- [ ] Cached real artwork appears for supported cards.
- [ ] Compact cards can be selected and inspected at full size.
- [ ] Changing the selected deck and relaunching changes the displayed cards.
- [ ] The preview does not imply that a real game has started.
- [ ] No XMage or Java gameplay gateway is required.
- [ ] Unity closes cleanly and Manaforge remains usable.
- [ ] Missing Unity build, missing artwork, malformed preview data and startup failures are handled without crashes or loss of user data.
- [ ] Repeated launch/close cycles do not leave owned Unity processes or temporary preview assets behind.
- [ ] Existing Qt Play, Deck Editor, Printer and Card Database behavior remains unchanged.
- [ ] Installed Play remains appropriately gated.

## Validation

Add deterministic acceptance coverage for:

- Real DeckDocument-to-preview projection.
- Format/printing preservation.
- Duplicate entries and quantities.
- Invalid and missing artwork.
- Preview mode contract validation.
- Owned Unity process startup and cleanup.
- Repeated launches and cancellation.
- Missing executable and failed startup.
- Existing module/navigation regressions.

Reuse existing C# EditMode/PlayMode tests where possible. Add graphics-enabled screenshot evidence using the existing Unity build/smoke infrastructure when the licensed runner is available.

**Codex testing policy:** Do not run routine tests locally. Use existing GitHub Actions CI. Do not weaken, skip or remove tests to obtain a green build. If licensed Unity CI is unavailable, report the evidence gap explicitly.

Owner manual acceptance must include launching Manaforge normally, selecting a real deck, opening the Unity preview, inspecting cards, closing Unity, and verifying that Manaforge still functions correctly.

## Out of Scope

Do not implement any of the following as part of this story:

- Live XMage gameplay.
- Rules enforcement or legal-action calculation.
- Actual shuffling, drawing, casting or combat.
- Mana payment or priority automation.
- AI gameplay.
- Networking or multiplayer.
- A complete Arena-quality battlefield redesign.
- Full-art and showcase-frame reconstruction.
- Unity embedding into the Qt window.
- Installer activation for general users.
- Any large unrelated refactoring.

## Completion and Handoff

Follow repository versioning rules in `AGENTS.md`.

Codex must report:

1. Files added or modified.
2. How the selected deck travels from Qt into the Unity preview.
3. Reused rendering, artwork and lifecycle components.
4. CI workflow results with links.
5. Any missing licensed-runner evidence.
6. Exact instructions for launching and visually testing the preview.
7. Remaining limitations and follow-up work toward P4.1.

**Definition of Done:** I can launch Manaforge, choose one of my actual decks, click Start Play Preview, and see that deck's cards rendered in a separate Unity window without using the Unity Editor or a terminal.

A standalone artwork fixture or Java/C# test does not satisfy this story. The user-facing Manaforge-to-Unity path must work.
