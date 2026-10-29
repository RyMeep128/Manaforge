# Card Database workspace

Open **Settings > Card Database** from the Manaforge home window. The resizable workspace stays available while shared database jobs run. Closing it hides it; reopening restores its filters, page, and active operation. Quitting Manaforge still cancels shared work through the existing shutdown path and waits for browser reads.

## Browse Cards

The browser reads only installed SQLite records, independently of a deck and without remote searches or automatic image downloads. Unique Cards returns one matching printing per Oracle identity; All Printings shows individual records with set, collector number, language, and frame effects. View local printings restricts results to the selected Oracle identity.

Search accepts the existing local syntax, including `o:draw`, `t:creature`, `c:u`, `id:wu`, `mv:3`, `r:rare`, `f:commander`, and `cn:123`. Dedicated fields expose common filters and set name/code. Ctrl+F focuses search; Ctrl+C copies the current name when the result list has focus. Results support extended selection, grid/list layouts, local face previews, and name copying.

Queries are debounced and cancellable. Each source page contains at most 60 records; thumbnails are read only for visible items and use the canonical image service. Missing Artwork checks each image-bearing face, including its actual recorded asset/file. Because this check is bounded to a source page, an empty page can still have a Next page. Unique mode checks its representative matching printing; use All Printings to inspect every printing's artwork.

Download scopes are selected printings, every local printing of selected cards, the entered set, or all filtered results across pages. A confirmation identifies the scope. Filtered unique-card downloads use the matching representative printing of each card. Full printing coverage requires All Printings or the selected-card scope. Multi-face downloads include every supported image-bearing face.

## Artwork

Missing/offline/retry actions use InstallationEngine's existing catalog-wide checkpointed artwork fill. Valid images are reused, changed local image URLs can be refreshed, and custom images remain protected. Retry resumes the shared checkpoint or scans the supported catalog again; it is not a separate failed-item queue. Selected downloads use CardService.cache_artwork with the existing per-printing locks, URL tracking, deduplication, verification, and Scryfall pacing. Selected scopes can be resumed within the retained workspace; after application restart, choose that scope again. Successful images are reused.

Storage usage is measured only on request. Audit artwork storage opens the existing safe audit/cleanup tools. Verify or repair artwork opens Diagnostics & Repair. Artwork preferences retain existing choices and favorites. No second artwork cache or schema is introduced.

## Maintenance

Existing dataset planning, size estimates, verified installation/activation, mode/location configuration, interrupted-install recovery, diagnostics, repairs, operation history, feedback, and report export remain available. Updates here are card datasets, not application releases. Path changes affect future writes and do not move existing libraries. First-run setup continues to use the original wizard.

Catalog counts are obtained once asynchronously when this retained workspace is constructed. Artwork storage scans are explicit. No completeness percentage, update-availability badge, or health status is inferred. After an explicit update check, Maintenance compares installed and available card dataset versions, and the header reports whether those checked card datasets differ. Artwork count and bytes appear in the header after an explicit storage inspection. Recommendation dataset versions remain in Maintenance; the header does not infer their update status.

## Validation status

New tests in the existing Core and integration CI collections cover local filters, unique/printing modes, pagination, Oracle scope, multi-face cache detection, selected download scope, cancellation, failed faces, shared-operation coordination, navigation, and workspace close behavior. Existing setup, installation, repair, and queue regression suites remain unchanged.

Tests were not run locally, as requested. This branch is intentionally not pushed, so CI cannot validate these changes yet. Windows visual review at multiple display scales and large-catalog performance acceptance remain pending. The story must not be marked fully accepted until that review and CI succeed.
