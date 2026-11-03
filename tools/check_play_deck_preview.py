"""Licensed-runner packaged preview smoke using generated public test data only."""

import json
from pathlib import Path
import sys
import tempfile
import time

sys.path[:0] = [
    str(Path(__file__).resolve().parents[1] / "Mtg_Projects"),
    str(Path(__file__).resolve().parents[1] / "Mtg_Projects/mtg_core"),
]
from PyQt6.QtGui import QImage
from mtg_core.decks import Deck, DeckDocument, DeckEntry
from mtg_play.deck_preview import DEFAULT_PLAYER, PreviewLaunch, prepare_preview


def main():
    output = DEFAULT_PLAYER.parents[2] / "Artifacts/DeckPreviewSmoke"
    output.mkdir(parents=True, exist_ok=True)
    image_path = output / "preview.png"
    if image_path.exists():
        image_path.unlink()
    with tempfile.TemporaryDirectory(prefix="manaforge-public-preview-") as source:
        image = QImage(160, 224, QImage.Format.Format_RGBA8888)
        image.fill(0xFF26774C)
        cached = Path(source) / "public.png"
        image.save(str(cached))

        class Service:
            def get_card(self, *, card_id):
                return dict(
                    id=card_id,
                    oracle_id="public-oracle",
                    name="Generated public preview",
                    layout="normal",
                    frame="2015",
                    border_color="black",
                    full_art=False,
                    textless=False,
                    promo=False,
                    type_line="Creature",
                    power="2",
                    toughness="2",
                    mana_cost="{G}",
                    oracle_text="Public CI artwork. No gameplay.",
                )

            def get_prints(self, *args, **kwargs):
                assert kwargs["allow_remote"] is False
                return []

            def get_image_path(self, *args, **kwargs):
                return str(cached)

        deck = DeckDocument(
            deck=Deck(
                name="Public CI preview",
                entries=[
                    DeckEntry(
                        "public-entry",
                        "Generated public preview",
                        3,
                        card_id="public-printing",
                        oracle_id="public-oracle",
                    )
                ],
            )
        )
        launch = PreviewLaunch()
        launch.root = Path(tempfile.mkdtemp(prefix="manaforge-deck-preview-"))
        try:
            payload = prepare_preview(deck, "freeform", Service(), launch.root)
            launch.owner.start_preview(
                [
                    str(DEFAULT_PLAYER),
                    "-manaforgeDeckPreview",
                    "1",
                    "-screen-fullscreen",
                    "0",
                    "-screen-width",
                    "1366",
                    "-screen-height",
                    "768",
                    "-logFile",
                    "NUL",
                    "-manaforgePreviewScreenshot",
                    str(image_path.resolve()),
                ],
                preview_bootstrap=payload,
                cwd=str(DEFAULT_PLAYER.parent),
            )
            deadline = time.monotonic() + 120
            ready = False
            while launch.owner.client_exit_code is None:
                if not ready and (launch.root / "preview-ready.json").exists():
                    launch.owner.client_ready()
                    ready = True
                if time.monotonic() > deadline:
                    raise RuntimeError("PUBLIC_PREVIEW_TIMEOUT")
                time.sleep(0.05)
            if (
                not ready
                or launch.owner.client_exit_code != 0
                or not image_path.exists()
                or image_path.stat().st_size < 1000
            ):
                raise RuntimeError("PUBLIC_PREVIEW_FAILED")
        finally:
            launch.close()
    (output / "report.json").write_text(
        json.dumps(
            dict(
                preview_only=True,
                public_generated_data=True,
                ready=True,
                exit_code=0,
                cleanup_confirmed=True,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
