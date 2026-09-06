# Printer setup and calibration

The current workflow exports PDFs. Printing itself happens in your PDF viewer and printer driver. Sheet occupancy warnings offer **Go Back** and **Print Anyway** before export; the app does not submit a printer job.

## Settings already remembered

**Save Project** persists page size, orientation, bleed, backside enablement, horizontal backside offset in millimetres, per-card short-edge rotation, and backside output ordering/separate-file settings. Reopening the project restores them. Printer-driver settings such as duplex mode and scaling are not controlled by the app.

## Named printer profiles

Open **Print Settings → Printer profiles…** to save the current paper size, orientation, backside enablement, horizontal backside offset, backside output ordering/separate-file settings, and duplex preference under a reusable name. Saving with an existing name offers to replace it; profiles can also be deleted.

Select a profile to inspect its settings, then choose **Apply selected profile** to review the changes and copy them into the active project. Later profile edits or deletion do not change saved projects. Manual placements are reconciled to the new sheet; impossible card footprints are rejected before changing the project. Applied settings use the existing project Save/autosave workflow.

Profiles are stored in `printer_profiles.json` in the application data directory (by default `%LOCALAPPDATA%\PrintProxyPrep`). The project's duplex preference is also saved and displayed in Print Settings. Choose Actual size / 100% and the corresponding duplex setting in your PDF viewer. This preference does not configure the printer driver or alter per-card short-edge rotation.

The existing horizontal offset is supported in millimetres. Vertical offsets remain a future change requiring preview, PDF placement, persistence, and tests together.

## Next: calibration PDF

- Generate a dedicated paired front/back PDF with labelled orientation arrows, registration marks, a millimetre ruler, and a measured reference rectangle.
- Instruct the user to print at actual size/100%, with fit-to-page disabled, using the intended paper and duplex setting.
- Let the user record measured horizontal/vertical misalignment and verify a second test page before saving a profile.
- Keep calibration separate from card projects and normal sheet-occupancy warnings. Never send a physical print job without an explicit print action.

Printer profiles are implemented; calibration PDF generation remains planned.
