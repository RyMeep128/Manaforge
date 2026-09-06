# Printer setup and calibration

The current workflow exports PDFs. Printing itself happens in your PDF viewer and printer driver. Sheet occupancy warnings offer **Go Back** and **Print Anyway** before export; the app does not submit a printer job.

## Settings already remembered

**Save Project** persists page size, orientation, bleed, backside enablement, horizontal backside offset in millimetres, per-card short-edge rotation, and backside output ordering/separate-file settings. Reopening the project restores them. Printer-driver settings such as duplex mode and scaling are not controlled by the app.

## Next: named printer profiles

- Store reusable profiles outside individual projects, with a name, paper size/orientation, duplex flip preference, and measured front/back alignment offsets.
- Applying a profile should show the changes, copy its settings into the active project, and preserve that project's saved settings independently of later profile edits.
- Start with the existing horizontal offset. Adding vertical offsets requires updating preview, PDF placement, persistence, and tests together.
- Do not claim to configure a printer driver: show the duplex and scaling settings the user must choose in the PDF viewer.

## Next: calibration PDF

- Generate a dedicated paired front/back PDF with labelled orientation arrows, registration marks, a millimetre ruler, and a measured reference rectangle.
- Instruct the user to print at actual size/100%, with fit-to-page disabled, using the intended paper and duplex setting.
- Let the user record measured horizontal/vertical misalignment and verify a second test page before saving a profile.
- Keep calibration separate from card projects and normal sheet-occupancy warnings. Never send a physical print job without an explicit print action.

Printer profiles and calibration generation are planned, not implemented in this update.
