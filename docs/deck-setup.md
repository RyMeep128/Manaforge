# Deck setup

New Deck (including Ctrl+N and the Print Studio project browser) opens a compact
setup dialog. Name is optional; format defaults to the last creation choice, or
Commander. Blank decks need only Create Deck. Import and precon starting points
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
visible and can be retained or removed. Association never uploads anything; Upload
to Library preselects the destination and uses the existing publication review,
authentication, capability, and permission checks.

No local tests or builds were run for this change. CI covers draft isolation,
commanderless theme persistence, manual organization preservation, unavailable
library associations, and explicit-theme ranking.

UX reference: [Archidekt's creation flow](https://archidekt.com/faq) keeps format,
name and optional destination choices together. Manaforge uses its existing dark
surfaces, accent buttons, artwork canvas and searchable theme controls.
