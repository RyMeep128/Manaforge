# Deck setup

New Deck (including Ctrl+N and the Print Studio project browser) opens a compact
setup dialog. Name is optional; format defaults to the last creation choice, or
Commander. Creation proceeds through starting point, optional commander, then themes and library, with Back and Next controls. Enter in commander search never creates a deck. Import and precon starting points
remain available in the same dialog.

Commander and Custom expose the existing local commander discovery search with
card artwork. Choose a primary commander, then use Partner / Background to search
compatible second commanders using the shared eligibility rules. Other formats
hide this section. Commander selection and themes are optional.

Themes are multiple explicit selections in the existing document metadata
(`editor_preferences.manual_themes`), independent of commander identity. The
shared theme catalog and card classifier provide suggestions. Explicit matching
themes receive twice the inferred-theme ranking bonus; they do not exclude other
recommendations. Existing legality and commander color filtering still apply.

Deck settings is available beside Card Search and in More. It edits a draft and
applies changes as one undoable command. Changing an established commander through
other editor controls offers a dismissible theme update dialog. Keeping existing
themes or pressing Escape leaves them unchanged. Initial setup does not show a
second theme dialog. Commander replacement uses the existing mutation path, which
moves former commanders to the mainboard and preserves manual organization.

Library association defaults to local and stores only destination identifiers and
name in `deck.library_association`. Signed-in or securely remembered connections
are offered without contacting a server. An unavailable saved association remains
visible and can be retained or removed. During creation, choosing a library uploads the saved deck through the existing publishing flow. A destination that needs sign-in opens the publishing dialog instead. Deck settings retain the destination for later uploads. Upload to Library also preselects that destination.

No local tests or builds were run for this change; validation is left to CI. CI covers draft isolation,
commanderless theme persistence, manual organization preservation, unavailable
library associations, and explicit-theme ranking.

UX reference: [Archidekt's creation flow](https://archidekt.com/faq) keeps format,
name and optional destination choices together. Manaforge uses its existing dark
surfaces, accent buttons, artwork canvas and searchable theme controls.

Precon selection happens before commander selection. Double-clicking a precon starts
its complete import; the imported commander is selected on the next step. Oversized
display commanders remain preserved in a separate Display Commander section, rather
than appearing in a functional or creature group with playable cards.

Community category sharing is opt-in per library: Browse Online > Libraries >
[library name] > Share manual categories when publishing decks. Only deliberate
manual category choices from published decks are contributed.

Browse Online opens shared decks as read-only card galleries. Make editable copy
creates an independent local deck; Follow deck keeps a revision-tracked offline copy.


Creation uses compact stacked pages with starting-point tiles and a stable footer.
Only blank/import Commander or Custom paths show commander search. A precon goes
straight from selection to themes and library, preserving its commander(s) and
showing a summary with commander artwork. Back returns to the starting point;
Next opens precon selection again. Commander changes remain available after creation.

Make editable copy opens the saved local deck immediately through the editor's
normal unsaved-change handling. Copies use `Deck Name [Library Name]`; the name
comes from the selected publication or followed deck's source, not another active
connection. Cancelling an editor switch leaves the saved copy in My Decks.


The finishing page explicitly shows the embedded theme and destination widgets after
removing them from their tabs. The precon summary has a bounded height so both
controls remain visible. Starting-point and precon-finishing pages use the local
theme catalog immediately; they do not run commander discovery to populate themes.
Commander searches run only on the commander page and cancel when leaving it.
