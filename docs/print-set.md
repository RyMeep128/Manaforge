# Print a set

Open **Print Studio → Print Set**, or **Add Cards → Print a set** in an
existing project. Search by a set's name or code and select it.

Choose **Set Cube** for four copies of each common, two of each uncommon,
and one of each rare and mythic. **One of Each** selects one copy per card.
Editing a rarity quantity switches to **Custom**; zero leaves that rarity out.
The summary updates as you change quantities.

**Additional options** includes basic lands, tokens, extra artwork versions,
and confirmed related sets such as bonus sheets. Select a related token set
and enable tokens to include its cards. Normally, multiple versions of the
same card contribute only one card to the collection. Enabling every artwork
version includes separate collector-number versions, while language editions
of the same version remain a single choice. Artwork preferences and favorites
choose among versions within the selected sets.

Use **Download / refresh set data** if a set has no local data or appears
incomplete. The online directory supplies expected counts and related-set
information when available. Offline catalogs without that information require
you to explicitly choose **Print the available cards only**. No completeness
claim is made for that selection.

**Review cards** is optional. Search or filter by rarity, inspect cached artwork,
and change an individual card's copies. Zero excludes it. Individual changes
take priority over rarity defaults until **Reset individual changes** is used.
Cards without available artwork must be updated or excluded before generation.

Select **Generate Print Project**. Artwork already in Manaforge's shared cache
is reused. Remaining artwork is downloaded in the background. Cancellation stops
after the current request; prepared artwork remains cached for retry. Failures
do not add a partially prepared project to the library or change existing projects.

The completed project opens in the normal Print Studio. Adjust artwork and print
settings, preview sheets, save, **Export PDF**, or **Print** as usual. Quantities,
individual changes, and the collection configuration are saved in the project.
Sheet estimates cover fronts; printing card backs requires additional sides.

## Implementation and validation

- `mtg_core.set_catalog` owns set discovery, catalog reads, and incremental updates.
- `mtg_print.set_inventory` builds collections independently of widgets or packs.
- `mtg_print.services.set_print_service` prepares artwork using the existing
  importer and publishes a standard project only after all selected assets verify.
- `mtg_ui.print_set_dialog` provides the guided experience with shared styling
  and loading infrastructure. Print Studio retains rendering, PDF, and printer control.
- `mtg_proxy/tests/test_print_set.py` covers discovery, presets, counts, identities,
  related cards, lands, tokens, double-faced cards, missing data, artwork failures,
  cancellation/retry, project reopening, Qt PDF inspection, and UI configuration.

The Python suite must run on GitHub Actions under the repository workflow.
Local syntax checks and rendered layout inspection are separate evidence and
do not establish automated-suite or live large-set acceptance.
