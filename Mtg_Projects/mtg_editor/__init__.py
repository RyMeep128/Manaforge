from mtg_editor.models import (
    DEFAULT_CATEGORY_ID,
    DEFAULT_SECTION,
    SCHEMA_VERSION,
    Category,
    DeckCard,
    DeckEditorPreferences,
    DeckMetadata,
    DeckProject,
)
from mtg_editor.catalog import (
    CatalogCardCandidate,
    resolve_deck_entry,
    search_catalog_cards,
)
from mtg_editor.decklist_io import (
    DecklistEntry,
    DecklistImportResult,
    export_decklist,
    import_decklist,
    import_decklist_file,
    parse_decklist,
    read_decklist_file,
    write_decklist_file,
)
from mtg_editor.project_store import (
    ProjectStoreError,
    create_project,
    load_project,
    save_project,
)
from mtg_editor.playtest import (
    PlaytestCard,
    PlaytestSession,
    append_playtest_note,
    build_playtest_library,
    draw_cards,
    mulligan,
    reset_playtest,
    start_playtest,
)
from mtg_editor.quick_add import (
    QuickAddQuery,
    QuickAddResult,
    add_catalog_candidate,
    parse_quick_add_input,
    quick_add_card,
    search_printings,
)
from mtg_editor.services import (
    CardFilters,
    CardGroup,
    compute_deck_stats,
    filter_cards,
    group_cards,
    sort_cards,
)

__all__ = [
    "DEFAULT_CATEGORY_ID",
    "DEFAULT_SECTION",
    "SCHEMA_VERSION",
    "CardFilters",
    "CardGroup",
    "CatalogCardCandidate",
    "Category",
    "DeckCard",
    "DeckEditorPreferences",
    "DeckMetadata",
    "DeckProject",
    "DeckEditorWidget",
    "DeckEditorWindow",
    "DecklistEntry",
    "DecklistImportResult",
    "PlaytestCard",
    "PlaytestSession",
    "ProjectStoreError",
    "QuickAddQuery",
    "QuickAddResult",
    "add_catalog_candidate",
    "append_playtest_note",
    "build_playtest_library",
    "compute_deck_stats",
    "create_project",
    "draw_cards",
    "export_decklist",
    "filter_cards",
    "group_cards",
    "import_decklist",
    "import_decklist_file",
    "load_project",
    "mulligan",
    "parse_decklist",
    "parse_quick_add_input",
    "quick_add_card",
    "read_decklist_file",
    "reset_playtest",
    "resolve_deck_entry",
    "run_editor",
    "save_project",
    "search_catalog_cards",
    "search_printings",
    "sort_cards",
    "start_playtest",
    "write_decklist_file",
]


def __getattr__(name):
    if name in {"DeckEditorWidget", "DeckEditorWindow", "run_editor"}:
        from mtg_editor.gui import DeckEditorWidget, DeckEditorWindow, run_editor

        gui_exports = {
            "DeckEditorWidget": DeckEditorWidget,
            "DeckEditorWindow": DeckEditorWindow,
            "run_editor": run_editor,
        }
        return gui_exports[name]
    raise AttributeError(f"module 'mtg_editor' has no attribute {name!r}")
