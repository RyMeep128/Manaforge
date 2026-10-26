# Things to test added on October 26, 2026

All items below are pending manual checks, not recorded passes. No local tests,
builds, or application checks were run to prepare this checklist. Use a disposable
data folder and copies of decks for failure/recovery checks. Record the application
version, result, and reproduction steps when reporting a problem.

## First priority: normal use

- [ ] Extract the complete Windows ZIP on a machine without Python/Git. Launch
  Manaforge with `_internal` beside the executable; Home opens without import or
  missing bundled-data errors.
- [ ] Complete first-run setup with **Download as needed**. Check download sizes
  before installing: estimates appear without starting installation. Finish opens Home.
- [ ] With existing data and no network, choose **Continue with existing data**.
  Existing favorites, decks, printing settings, and cached artwork remain usable.
- [ ] Create a blank deck, import a normal decklist, save, close, and reopen it.
  Opening Quick Add on an empty deck stays in search; reopening the full search
  workspace remembers its selected tab.

## Create from Precon

- [ ] Open **New deck → Create from Precon** from the project browser, recent-deck
  menu, and Ctrl+N chooser. Blank creation and normal import still work.
- [ ] Search by deck/product name, commander, set, and year. Combine format,
  release-year, and color filters. Products with unknown colors remain available
  without a color filter. Commander products appear first.
- [ ] Resize the browser: commander/featured-card tiles wrap and retain readable
  deck labels. Missing artwork shows a usable placeholder; scrolling stays responsive.
- [ ] Preview a product, rename it, review its import, and create it. Compare names,
  quantities, zones, and source printings with the original list. Try a partner deck
  and a product with sideboard, planar/scheme, or display-commander sections;
  display commanders should be marked do-not-print.
- [ ] Try missing local card data with online fetching disabled, then enabled.
  Unresolved printings prevent partial deck creation. Cancel preserves the active deck.
- [ ] Edit, undo/redo, save/reopen, and export the created deck. Its original-list
  provenance remains intact; creating it again gives an independent original deck.

## Card quantities, metadata, and discovery

- [ ] Add/remove copies from the deck, Quick Add, search, recommendations, discovery,
  and card-details preview. Counts agree, one edit undoes/redoes correctly, and zero
  removes the intended entry. Candidate removal does not depend on deck selection.
- [ ] Try alternate printings, multi-face names, commander copies, and mainboard
  copies of the same card. Identity counts agree while exact-print additions keep
  their intended printing. Commander/companion references clear when removed.
- [ ] Check quantity buttons at several card sizes and in narrow windows. Visible
  buttons and click targets agree; flip controls remain usable.
- [ ] Import and inspect a card, then discover from it. Faces, roles, keywords,
  legality, and commander colors agree across views. Unknown identity remains
  distinct from known colorless; pregame color choices affect Commander filtering.
- [ ] Type ordinary names, Boolean syntax, and incomplete syntax in Quick Add and
  search. Syntax detection agrees with Print Studio search. Add several discovery
  results without losing the selected seed, results, face, or scroll position.
- [ ] Select an explicit EDHREC audience with published data, then one unavailable
  locally. Exact cohorts are used; only automatic selection may fall back to general
  with a status explanation. Custom Oracle-tag themes do not select EDHREC cohorts.

## Data Management and artwork

- [ ] Check for updates and apply available card, rulings, recommendation, and precon
  catalog updates. Installed versions refresh and existing personal data survives.
  An unavailable optional precon refresh retains the prior catalog.
- [ ] In on-demand mode, view uncached cards and both faces online, then reopen them
  offline. Cached and user-selected artwork survives updates.
- [ ] On a suitably sized disposable library, start a full-offline artwork fill;
  pause, resume, and restart it. Progress remains responsive and completed downloads
  are reused. This does not require downloading the entire artwork catalog.
- [ ] Interrupt an update or use an unavailable connection. The previous working
  library remains usable and retry resumes safely. Closing an owning update dialog
  cancels safely; closing an observer leaves the shared update running.
- [ ] Change the future artwork location and clear optional copies. Referenced old
  artwork remains accessible; canonical artwork, decks, and settings remain intact.
- [ ] With automatic updates due, check normal startup and explicit offline mode.
  Offline mode prevents automatic network work; manual update controls remain usable.

## Diagnostics, repair, and feedback

- [ ] Open diagnostics from Home/Data Management. Review findings, export a local
  report, and confirm local paths and recognizable secrets are redacted.
- [ ] In a disposable installation with a missing/damaged managed dataset, review
  and run an offered repair. Cancel/retry safely; preserve user decks and preferences.
- [ ] Open **Help → Send Feedback** in Home, Deck Editor, and Print Studio. Empty
  title/description is rejected. Preparing diagnostics leaves upload consent unchecked.
- [ ] Save a draft, restart, reopen **Pending Feedback**, edit, and delete it.
  Pending reports never upload automatically. Failed submission retains the report.
- [ ] Attach/remove a PNG/JPEG; reject invalid or oversized files. Review and cancel
  sending: no upload occurs. Confirm the review shows destination and attachments.
- [ ] With a separately configured staging relay, explicitly send a report and retry
  after a connection failure. Successful submission returns a reference without
  duplicate issues; GitHub receives only category/version/reference metadata. Without
  relay configuration, saving drafts works and sending explains the failure.

## CI / maintainer follow-up

- [ ] Review CI results for Python suites and feedback-relay checks after push.
- [ ] When a Windows build is explicitly requested, review the packaged executable
  diagnostic and manually try the resulting ZIP. A source push alone does not
  establish packaged-app success.
- [ ] Validate recommendation manifests/archives and activation using the existing
  distribution workflow when publishing data is separately requested. A normal
  checklist commit does not publish application or dataset releases.

See [installation](installation-and-updates.md), [precons](preconstructed-decks.md),
[shared operations](shared-components.md), and [feedback setup](../feedback-relay/README.md)
for expected behavior and prerequisites. Earlier regression scenarios remain in
[recent-change QA](recent-change-qa.md).
