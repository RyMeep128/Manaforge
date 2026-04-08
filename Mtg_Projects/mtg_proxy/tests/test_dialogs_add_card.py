import dialogs
import high_res
from constants import APP_VERSION
from services import deck_import_service


class _FakeLabel:
    def __init__(self):
        self.value = ""

    def setText(self, value):
        self.value = value


class _FakePageStack:
    def __init__(self):
        self.index = 0

    def setCurrentIndex(self, index):
        self.index = index


class _FakeAddCardDialogState:
    def __init__(self):
        self._selected_art_candidate_value = None
        self._art_summary_label = _FakeLabel()
        self._selected_card_value = type(
            "Candidate",
            (),
            {
                "name": "Opt",
                "set_name": "Tenth Edition",
                "set_code": "10e",
                "collector_number": "94",
            },
        )()
        self._selected_card_label = _FakeLabel()
        self._page_stack = _FakePageStack()
        self.accepted = False

    def _candidate_summary_text(self, candidate):
        return dialogs.AddCardDialog._candidate_summary_text(self, candidate)

    def _selected_card_candidate(self):
        return self._selected_card_value

    def _update_art_summary(self):
        return dialogs.AddCardDialog._update_art_summary(self)

    def accept(self):
        self.accepted = True


class _FakePreviewLabel:
    def __init__(self):
        self.text = ""
        self.pixmap = None

    def setText(self, value):
        self.text = value

    def setPixmap(self, value):
        self.pixmap = value

    def size(self):
        return (120, 168)


class _FakePreviewDialogState:
    def __init__(self):
        self._card_preview_cache = {}
        self._card_preview_label = _FakePreviewLabel()
        self.warnings = []

    def _run_with_popup(self, _title, work):
        work()

    def _warn(self, title, message):
        self.warnings.append((title, message))


def test_add_card_dialog_uses_default_art_summary_when_no_custom_art_is_selected():
    dialog_state = _FakeAddCardDialogState()

    dialogs.AddCardDialog._update_art_summary(dialog_state)

    assert dialog_state._art_summary_label.value == "Art choice: Default Scryfall import art"


def test_crash_report_includes_app_version():
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        report = dialogs.format_exception_report(type(exc), exc, exc.__traceback__)

    assert f"App Version: {APP_VERSION}" in report


def test_add_card_dialog_shows_custom_art_summary():
    dialog_state = _FakeAddCardDialogState()
    dialog_state._selected_art_candidate_value = high_res.HighResCandidate(
        identifier="art-1",
        name="Opt",
        dpi=1200,
        extension="png",
        download_link="https://example.test/opt.png",
        small_thumbnail_url="thumb",
        medium_thumbnail_url="preview",
        source_id=1,
        source_name="MPCFill",
        art_source="mpcfill",
    )

    dialogs.AddCardDialog._update_art_summary(dialog_state)

    assert dialog_state._art_summary_label.value == "Art choice: Custom art from MPCFill [1200 DPI]"


def test_add_card_dialog_adds_selected_card_without_art_step():
    dialog_state = _FakeAddCardDialogState()

    dialogs.AddCardDialog._go_to_art_step(dialog_state)

    assert dialog_state.accepted is True
    assert dialog_state._page_stack.index == 0


def test_add_card_dialog_thumbnail_loader_prefers_local_image_path(monkeypatch):
    captured = {}

    class _FakeList:
        def item(self, _row):
            return None

    class _FakeLoader:
        def __init__(self, page_token, pending):
            captured["page_token"] = page_token
            captured["pending"] = pending
            self.thumbnail_loaded = type("Signal", (), {"connect": lambda *_args: None})()
            self.finished = type("Signal", (), {"connect": lambda *_args: None})()

        def start(self):
            captured["started"] = True

    dialog_state = type(
        "DialogState",
        (),
        {
            "_card_thumbnail_loader": None,
            "_card_thumbnail_cache": {},
            "_card_thumbnail_page_token": 0,
            "_card_results_list": _FakeList(),
            "_card_candidates": [],
            "_stop_card_thumbnail_loader": lambda self: dialogs.AddCardDialog._stop_card_thumbnail_loader(self),
            "_card_thumbnail_key": lambda self, candidate: dialogs.AddCardDialog._card_thumbnail_key(self, candidate),
            "_card_thumbnail_sources": lambda self, candidate: dialogs.AddCardDialog._card_thumbnail_sources(self, candidate),
            "_apply_card_thumbnail": lambda self, row, candidate, data: dialogs.AddCardDialog._apply_card_thumbnail(self, row, candidate, data),
            "_handle_card_thumbnail_loaded": lambda self, page_token, identifier, data: dialogs.AddCardDialog._handle_card_thumbnail_loaded(self, page_token, identifier, data),
        },
    )()
    candidate = deck_import_service.ScryfallCardCandidate(
        name="Opt",
        set_code="eld",
        set_name="Throne of Eldraine",
        collector_number="59",
        card_id="card-opt",
        oracle_id="oracle-opt",
        scryfall_id="card-opt",
        preview_url="preview-url",
        thumbnail_url="thumb-url",
        filename="scryfall_eld_59_opt.png",
        art_context=high_res.CardContext(
            filename="scryfall_eld_59_opt.png",
            query="Opt",
            display_name="Opt",
            set_code="eld",
            collector_number="59",
        ),
        card_data={},
        image_asset_id="asset-opt",
        local_image_path="local-opt.png",
    )

    monkeypatch.setattr(dialogs, "CardSearchThumbnailLoader", _FakeLoader)
    monkeypatch.setattr(
        dialogs.high_res_service,
        "get_cached_thumbnail_bytes",
        lambda _url: (_ for _ in ()).throw(AssertionError("remote thumbnail cache should not be checked")),
    )

    dialogs.AddCardDialog._start_card_thumbnail_loader(dialog_state, [candidate])

    assert captured["started"] is True
    assert captured["pending"] == [(0, "asset:asset-opt", "local-opt.png", "thumb-url")]


def test_add_card_dialog_thumbnail_loader_uses_remote_url_when_local_missing(monkeypatch):
    captured = {}

    class _FakeList:
        def item(self, _row):
            return None

    class _FakeLoader:
        def __init__(self, page_token, pending):
            captured["page_token"] = page_token
            captured["pending"] = pending
            self.thumbnail_loaded = type("Signal", (), {"connect": lambda *_args: None})()
            self.finished = type("Signal", (), {"connect": lambda *_args: None})()

        def start(self):
            captured["started"] = True

    dialog_state = type(
        "DialogState",
        (),
        {
            "_card_thumbnail_loader": None,
            "_card_thumbnail_cache": {},
            "_card_thumbnail_page_token": 0,
            "_card_results_list": _FakeList(),
            "_card_candidates": [],
            "_stop_card_thumbnail_loader": lambda self: dialogs.AddCardDialog._stop_card_thumbnail_loader(self),
            "_card_thumbnail_key": lambda self, candidate: dialogs.AddCardDialog._card_thumbnail_key(self, candidate),
            "_card_thumbnail_sources": lambda self, candidate: dialogs.AddCardDialog._card_thumbnail_sources(self, candidate),
            "_apply_card_thumbnail": lambda self, row, candidate, data: dialogs.AddCardDialog._apply_card_thumbnail(self, row, candidate, data),
            "_handle_card_thumbnail_loaded": lambda self, page_token, identifier, data: dialogs.AddCardDialog._handle_card_thumbnail_loaded(self, page_token, identifier, data),
        },
    )()
    candidate = deck_import_service.ScryfallCardCandidate(
        name="Opt",
        set_code="eld",
        set_name="Throne of Eldraine",
        collector_number="59",
        card_id="card-opt",
        oracle_id="oracle-opt",
        scryfall_id="card-opt",
        preview_url="preview-url",
        thumbnail_url="thumb-url",
        filename="scryfall_eld_59_opt.png",
        art_context=high_res.CardContext(
            filename="scryfall_eld_59_opt.png",
            query="Opt",
            display_name="Opt",
            set_code="eld",
            collector_number="59",
        ),
        card_data={},
    )

    monkeypatch.setattr(dialogs.get_default_card_service(), "get_image_path", lambda _card_id: None)
    monkeypatch.setattr(dialogs.high_res_service, "get_cached_thumbnail_bytes", lambda _url: None)
    monkeypatch.setattr(dialogs, "CardSearchThumbnailLoader", _FakeLoader)

    dialogs.AddCardDialog._start_card_thumbnail_loader(dialog_state, [candidate])

    assert captured["started"] is True
    assert captured["pending"] == [(0, "card:card-opt", None, "thumb-url")]


def test_add_card_dialog_preview_does_not_mutate_frozen_candidate(monkeypatch):
    dialog_state = _FakePreviewDialogState()
    candidate = deck_import_service.ScryfallCardCandidate(
        name="Opt",
        set_code="eld",
        set_name="Throne of Eldraine",
        collector_number="59",
        card_id="card-opt",
        oracle_id="oracle-opt",
        scryfall_id="card-opt",
        preview_url="preview-url",
        thumbnail_url="thumb-url",
        filename="scryfall_eld_59_opt.png",
        art_context=high_res.CardContext(
            filename="scryfall_eld_59_opt.png",
            query="Opt",
            display_name="Opt",
            set_code="eld",
            collector_number="59",
        ),
        card_data={},
        local_image_path=None,
    )

    monkeypatch.setattr(dialogs.get_default_card_service(), "get_image_path", lambda _card_id: None)
    monkeypatch.setattr(dialogs.high_res_service, "fetch_preview_bytes", lambda *_args, **_kwargs: b"not-a-real-image")
    class _FakePixmap:
        def loadFromData(self, _data):
            return True

        def scaled(self, *_args, **_kwargs):
            return self

    monkeypatch.setattr(dialogs, "QPixmap", _FakePixmap)

    dialogs.AddCardDialog._update_card_preview(dialog_state, candidate)

    assert candidate.local_image_path is None
    assert dialog_state.warnings == []
