# Printer setup and calibration

Manaforge supports PDF export and direct printing through the operating-system printer dialog. Sheet occupancy warnings offer **Go Back** and **Print Anyway** before either action. Direct printing creates a temporary document through the same renderer used by export; it submits a job only after the system dialog's final **Print** action.

## Settings already remembered

**Save Project** persists page size, orientation, bleed, backside enablement, horizontal and vertical backside offsets in millimetres, per-card short-edge rotation, and backside output ordering/separate-file settings. Reopening the project restores them. Printer-driver settings such as duplex mode and scaling are not controlled by the app.

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

Choose **Print** in the project toolbar, then select fronts and backs, fronts only, or backs only. Manaforge validates layout capacity and warns about under-filled sheets before rendering. The native printer dialog then provides installed-printer selection, copies, page range, and driver-specific properties. The active project or printer profile supplies the initial paper size, orientation, and duplex edge.

The print job is rasterized at the highest printer-supported resolution up to 600 DPI, one page at a time, from the shared PDF geometry. Printer rejection, invalid page ranges, and rendering failures are reported in the UI. Low-resolution artwork and missing-back preflight details remain the next direct-print increment.
