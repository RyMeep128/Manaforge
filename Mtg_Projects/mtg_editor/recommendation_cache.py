"""Explicit personal aggregate transfers; never starts public deck collection."""

from pathlib import Path

from PyQt6 import QtWidgets as W

from mtg_core.recommendation_cache import (
    download_cache,
    export_cache,
    read_cache,
    set_mode,
    write_cache,
)
from mtg_core.recommendations import RecommendationStore


def manage_cache(editor):
    actions = [
        "Use live collected cache",
        "Use imported personal cache",
        "Disable primary recommendations",
        "Export personal aggregate cache",
        "Import personal aggregate cache",
        "Download personal aggregate cache",
        "Use offline EDHREC cache",
    ]
    action, accepted = W.QInputDialog.getItem(
        editor,
        "Recommendation cache",
        "Personal use only. These controls do not stop or restart the collector.",
        actions,
        editable=False,
    )
    if not accepted:
        return
    root = editor.recommendation_store().path.parent
    destination = root / "archidekt.aggregate.json.gz"
    if action == "Use offline EDHREC cache":

        def select_edhrec():
            if not (root / "edhrec.sqlite3").exists():
                raise ValueError(
                    "Run tools/collect_edhrec.py to download the one-time snapshot first."
                )
            set_mode(root, "edhrec")
            return "Offline EDHREC selected. Reopen recommendations to apply."

        work = select_edhrec
    elif action in actions[:3]:
        mode = ["live", "portable", "disabled"][actions.index(action)]

        def select():
            if mode == "portable":
                read_cache(destination)
            set_mode(root, mode)
            return "Primary source selection saved. Reopen recommendations to apply."

        work = select
    elif action == actions[3]:
        path, _ = W.QFileDialog.getSaveFileName(
            editor,
            "Export personal aggregates",
            "archidekt.aggregate.json.gz",
            "Aggregate cache (*.json.gz)",
        )
        if not path:
            return

        def export():
            public = root / "archidekt.sqlite3"
            if not public.exists():
                raise ValueError("No collected public dataset is available")
            if Path(path).resolve() == public.resolve():
                raise ValueError("Choose a separate archive file")
            digest = export_cache(RecommendationStore(public), path)
            return f"Personal aggregate archive saved. No raw decks were exported.\nSHA-256: {digest}"

        work = export
    elif action == actions[4]:
        path, _ = W.QFileDialog.getOpenFileName(
            editor, "Import personal aggregates", "", "Aggregate cache (*.json.gz)"
        )
        if not path:
            return

        def import_file():
            write_cache(destination, read_cache(path))
            set_mode(root, "portable")
            return "Validated personal cache imported and selected. Reopen recommendations to apply."

        work = import_file
    else:
        url, accepted = W.QInputDialog.getText(
            editor,
            "Personal cache download",
            "HTTPS URL for your aggregate archive (no public feed is configured):",
        )
        if not accepted or not url.strip():
            return
        digest, accepted = W.QInputDialog.getText(
            editor, "Verify personal cache", "Expected SHA-256 from the archive export:"
        )
        if not accepted:
            return

        def download():
            download_cache(url.strip(), digest.strip(), destination)
            set_mode(root, "portable")
            return "Checksum-verified personal cache downloaded and selected. Reopen recommendations to apply."

        work = download
    editor.run_task(
        work,
        lambda message: W.QMessageBox.information(
            editor, "Recommendation cache", message
        ),
    )
