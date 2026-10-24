# Printer setup and calibration

Manaforge supports PDF export and direct printing through the operating-system printer dialog. Sheet occupancy warnings offer **Go Back** and **Print Anyway** before either action. Direct printing creates a temporary document through the same renderer used by export; it submits a job only after the system dialog's final **Print** action.

## Settings already remembered

**Save Project** persists page size, orientation, bleed, backside enablement, horizontal and vertical backside offsets in millimetres, per-card short-edge rotation, and backside output ordering/separate-file settings. Reopening the project restores them. Printer-driver settings such as duplex mode and scaling are not controlled by the app.

## Shared artwork preferences

Artwork choices have their own shared preference editor: **Preferences > Artwork
preferences** in Core, **More > Artwork preferences** in Editor, and **Preferences**
in the artwork picker. Existing artwork profiles remain readable and are upgraded
to versioned storage when saved. Invalid profiles or profiles from an unsupported
version report an error and remain unchanged. Unknown preference fields survive
edits, and Cancel never upgrades or rewrites a profile.

In an already-open artwork picker, **Search** reloads shared rules and the card's
favorite printing before fetching results. Page navigation does the same; if
preferences changed in another app, results restart at page one and show an update
notice. A Min DPI value you adjusted in this picker is retained. Otherwise the
latest shared minimum is used, with Max DPI raised if needed to keep the range
valid. Saving through **Preferences** resumes using the active rules' minimum
(the project minimum when an override exists). Refreshing
results does not replace project artwork; **Apply** or **Select Art** is still
required. Failed preference reads/searches report the error and clear selectable
results so an earlier search cannot be mistaken for the refreshed one.

Returning focus to the artwork picker checks shared preferences in the background.
If another app changed the rules or favorite printing, a notice offers **Search**
to refresh. The check is local and leaves the current selection, filters, and
artwork unchanged. A failed check shows a retry notice rather than opening a
warning dialog. Results from a check started before a newer search, focus change,
or dialog closure cannot replace the current notice.

## Deck and project artwork rules

Use **More > Deck artwork preferences** in Editor or **Print Settings > Project
artwork preferences** in Proxy. Uncheck **Use global preferences** to edit a full
set of rules for this deck/project. Save stores the override with the document;
Cancel leaves it unchanged. Check **Use global preferences** and Save to remove
the override and inherit the latest global rules again. Editor changes and resets
are one Undo/Redo step.

These rules affect artwork-picker ranking and DPI defaults, preferred-artwork
replacement previews, and the printings chosen for recommendations. They never
replace already-selected card artwork automatically. An explicit printing choice
and a global favorite still take precedence, including when a favorite matches
an avoidance rule. The picker identifies when project rules are active; its
**Preferences** button continues to edit global rules for other projects.

Overrides survive deck saves, print handoff, Proxy saves, and opening a print
project as a deck. A repeat **Print Deck** copies the deck's current artwork-rule
override (or global inheritance) into the linked print project. Existing print
settings still follow their separate linked-project behavior. Global rules may
change without affecting an override; favorite changes still trigger picker notices.

## Global printing defaults

Open **Global printing defaults** from Core's **Preferences** menu, Editor's
**More** menu, or Proxy's **Print Settings**. This shared editor saves paper size,
orientation, duplex preference, back enablement, X/Y back offsets, and back-page
ordering/separate-file options in Core. Save validates the values; Cancel leaves
them unchanged. Failed saves keep the dialog open for correction or retry.

New managed print projects and new Proxy drafts read the latest saved defaults.
Until defaults are saved, existing configuration supplies the initial paper size.
Existing projects, recovered drafts, imported project settings, and repeat Editor
handoffs retain their own settings. Bleed, artwork, guides, and driver-controlled
copies/color are outside these defaults.

To copy current global defaults into an existing print project, open **Print
Settings > Printer profiles > Reset project to global defaults**. Review the
changes before applying. The normal profile workflow reconciles placements and
rejects impossible layouts before changing the project. This copies settings;
it does not create a live link to future global edits. Reopen the defaults editor
to see changes saved by another Manaforge app.

## Named printer profiles

Open **Print Settings > Printer profiles...** to save the current paper size, orientation, backside enablement, horizontal and vertical backside offsets, backside output ordering/separate-file settings, and duplex preference under a reusable name. Saving with an existing name offers to replace it; profiles can also be deleted.

Select a profile to inspect its settings, then choose **Apply selected profile** to review the changes and copy them into the active project. Later profile edits or deletion do not change saved projects. Manual placements are reconciled to the new sheet; impossible card footprints are rejected before changing the project. Applied settings use the existing project Save/autosave workflow.

Profiles are stored in `printer_profiles.json` in the application data directory (by default `%LOCALAPPDATA%\PrintProxyPrep`). The project's duplex preference is also saved and displayed in Print Settings. Choose Actual size / 100% and the corresponding duplex setting in your PDF viewer. This preference does not configure the printer driver or alter per-card short-edge rotation.

Horizontal and vertical corrections use millimetres. Positive X moves backs right and positive Y moves backs up. Preview and PDF export use the same values.

## Calibration PDF

Open **Print Settings > Calibrate printer...**. The dialog uses the active paper size, orientation, bleed, and duplex preference to create a paired front/back PDF with orientation arrows, registration marks, a millimetre scale, a reference rectangle, and a full 3 x 3 sheet of cuttable 63 x 88 mm card-size targets. Solid lines show the finished card size; the configured bleed is recorded in the footer.

Print the PDF at Actual size / 100% with fit-to-page disabled. Hold the result to a light, measure the displacement, and enter the correction needed to move the back onto the front. Cut one target on its solid line and compare it with a physical card to verify scale and trimming. Save another PDF to verify the correction. Apply it to the project, or apply it and save all current print settings as a named profile.

Calibration remains separate from card sheets and does not submit a physical print job.

## Direct printing

Choose **Print** in the project toolbar, then select fronts and backs, fronts only, or backs only. Manaforge validates layout capacity and reviews under-filled sheets, low-resolution artwork, missing backs, bleed clipping risks, missing images, and invalid layouts before rendering. Valid output keeps **Print Anyway**; missing images and impossible layouts must be fixed first. The native printer dialog then provides installed-printer selection, copies, page range, and driver-specific properties. The active project or printer profile supplies the initial paper size, orientation, and duplex edge.

The print job is rasterized at the highest printer-supported resolution up to 600 DPI, one page at a time, from the shared PDF geometry. Printer rejection, invalid page ranges, and rendering failures are reported in the UI.

## More exports and presets

Choose **More Exports** to save every populated sheet as PNG or JPEG, export the unique prepared card fronts and backs, or create a ZIP containing sheets, cards, and a settings manifest. Raster sheet exports offer DPI control; PNG supports a transparent page background and JPEG supports quality control. Filenames are numbered deterministically, and sheet images use the same PDF renderer and placements as preview and printing.

Choose **Apply Print Preset** for validated Letter 3 x 3, A4 3 x 3, duplex Letter, 3 mm bleed, cut-guide, and oversized-card settings. Applying a preset reconciles manual placements before changing the active project and reports any moved copies.
