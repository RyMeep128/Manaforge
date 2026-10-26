"""Explicit personal aggregate transfers; never starts public deck collection."""

from pathlib import Path

from PyQt6 import QtWidgets as W

from mtg_core.recommendation_cache import (
    download_cache,
    export_cache,
    read_cache,
    set_mode,
    source_settings,
    save_source_settings,
    write_cache,
)
from mtg_core.recommendations import RecommendationStore
from mtg_core.public_deck_datasets import DATASET_LABELS


def manage_cache(editor):
    actions = [
        "Configure recommendation sources",
        "Export personal aggregate cache",
        "Import personal aggregate cache",
        "Download personal aggregate cache",
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
    if action == actions[0]:
        configure_sources(editor, root)
        return
    elif action == actions[1]:
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
    elif action == actions[2]:
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


def configure_sources(editor, root):
    """Independent public switches; local preferences remain saved per deck."""

    def show(loaded):
        config, cohort_choices = loaded
        dialog = W.QDialog(editor)
        dialog.setWindowTitle("Recommendation sources")
        layout = W.QFormLayout(dialog)
        archidekt = W.QCheckBox("Enable Archidekt recommendations")
        archidekt.setChecked(config["archidekt"]["enabled"])
        cache = W.QComboBox()
        cache.addItem("Live collected cache", "live")
        cache.addItem("Portable personal aggregate", "portable")
        cache.setCurrentIndex(cache.findData(config["archidekt"]["cache"]))
        edhrec = W.QCheckBox("Enable offline EDHREC recommendations")
        edhrec.setChecked(config["edhrec"]["enabled"])
        cohort = W.QComboBox()
        cohort.addItem("Automatic: match deck theme", "auto")
        cohort.addItem("General commander recommendations", "general")
        for kind, value, label in cohort_choices:
            cohort.addItem(f"{kind.title()}: {label}", f"{kind}:{value}")
        selected = config["edhrec"].get("cohort", "auto")
        if cohort.findData(selected) < 0:
            cohort.addItem(f"{selected} (not cached yet)", selected)
        cohort.setCurrentIndex(cohort.findData(selected))
        moxfield = W.QCheckBox("Enable Moxfield recommendations")
        moxfield.setChecked(config["moxfield"]["enabled"])
        layout.addRow(archidekt)
        layout.addRow("Archidekt data source", cache)
        layout.addRow(edhrec)
        layout.addRow("EDHREC cohort", cohort)
        layout.addRow(moxfield)
        dataset_controls = {}
        for source, label in DATASET_LABELS.items():
            checkbox = W.QCheckBox(f"Enable {label} recommendations")
            checkbox.setChecked(config[source]["enabled"])
            layout.addRow(checkbox)
            dataset_controls[source] = checkbox
        note = W.QLabel(
            "Available datasets contribute to one list. These controls never download data. Local supplement preferences are saved with each deck."
        )
        note.setWordWrap(True)
        layout.addRow(note)
        buttons = W.QDialogButtonBox(
            W.QDialogButtonBox.StandardButton.Save
            | W.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != W.QDialog.DialogCode.Accepted:
            return
        updated = dict(
            version=2,
            archidekt=dict(enabled=archidekt.isChecked(), cache=cache.currentData()),
            edhrec=dict(enabled=edhrec.isChecked(), cohort=cohort.currentData()),
            moxfield=dict(enabled=moxfield.isChecked()),
            **{
                source: dict(enabled=checkbox.isChecked())
                for source, checkbox in dataset_controls.items()
            },
        )
        def saved(_):
            panel = getattr(editor, "recommendation_panel", None)
            if panel is not None:
                panel.request_refresh()

        editor.run_task(lambda: save_source_settings(root, updated), saved)

    def load():
        from mtg_core.edhrec_cohorts import cohort_options

        return source_settings(root), cohort_options(root / "edhrec-cohorts.sqlite3")

    editor.run_task(load, show)
