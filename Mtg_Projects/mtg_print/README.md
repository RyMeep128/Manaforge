# Shared printing boundary

`mtg_print` contains printing operations used by both Editor and Proxy. It has
no Qt, PDF-renderer, or Proxy-module dependency. Shared configuration preserves
the existing data directory and `config.ini`; resource lookup still supports
Proxy's bundled assets and frozen application paths.

| Module | Responsibility |
| --- | --- |
| `project.py` | Deck-to-print payload conversion, preserving artwork, backs, layout settings, and embedded deck metadata |
| `layout.py` | Copy placement, reconciliation, moves, history, occupancy, page/grid distribution, and duplex page sequencing |
| `card_layouts.py` | Physical layout policy and printed-back detection |
| `models.py` | Project state, print settings, card metadata, and legacy serialization |
| `library.py`, `storage.py` | Project library, drafts, recovery snapshots, and atomic JSON writes |
| `config.py`, `paths.py` | Existing configuration singleton and compatible data/resource locations |
| `geometry.py` | Shared paper/card dimensions and unit conversions |
| `image.py`, `runtime_images.py` | Image processing, asset materialization, and preview caching |
| `deck_import.py`, `high_res.py` | Card-image import, artwork search, and artwork application |
| `services/`, `legacy_project.py` | Print import/artwork workflows and legacy project operations |

Placement functions accept a project-state object with the existing attributes
and accessors (`cards`, `get_card_entry`, `get_card_metadata`, print layout and
duplex settings). Proxy's `pdf` functions
retain dictionary-to-state conversion and delegate geometry here; its existing
`services.layout_service` and `card_layouts` modules retain compatibility imports.
Editor imports shared payload conversion, state, library, and placement directly.
Legacy Proxy `models`, `config`, `project_library`, and `fallback_image` imports
alias their shared modules so class identity, the mutable configuration singleton,
and existing replacement hooks stay consistent regardless of import order.

Qt dialogs and thumbnail workers live in `mtg_ui.print_dialogs` and
`mtg_ui.print_tasks`; Proxy retains import aliases. Editor uses these package
imports and no longer adds the Proxy application directory to `sys.path`.
Application launchers still establish their source-checkout package roots.
The shared dialogs read Proxy's version/resource constants through the normal
`mtg_proxy.constants` package import; non-UI printing code does not import Qt.
`integration_tests/test_shared_print_boundary.py` checks shared imports in an
isolated interpreter that rejects Qt and legacy Proxy module imports, plus a
separate dialog-import check without Proxy's directory on the import path.
