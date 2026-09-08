from services import deck_import_service
from models import ProjectState
import deck_import
import high_res
from mtg_core import CardService, RemoteLookupUnavailable
from pathlib import Path
import uuid


def test_local_syntax_search_does_not_fetch_remote_data(tmp_path, monkeypatch):
    def no_network(*args):
        raise AssertionError('Local-only search contacted the network')
    service = CardService(db_path=str(tmp_path / 'local.sqlite3'),
                          fetch_json_fn=no_network, fetch_bytes_fn=no_network)
    service.database.upsert_card_payload(dict(id='local', oracle_id='oracle-local',
        name='Test Scholar', type_line='Creature', oracle_text='Draw a card.',
        colors=['U'], color_identity=['U'], cmc=2, set='test', collector_number='1'))
    monkeypatch.setattr(deck_import_service, '_build_card_service', lambda *a: service)
    page = deck_import_service.search_scryfall_card_page('t:creature o:"draw a card" c:u mv<=2', local_only=True)
    assert page.search_source == 'local'
    assert [c.card_id for c in page.candidates] == ['local']
    assert page.candidates[0].card_data['oracle_text'] == 'Draw a card.'


def test_local_search_only_builds_requested_page_plus_lookahead(monkeypatch):
    calls = []
    results = [type('Result', (), {'card_id': str(i), 'oracle_id': str(i),
        'payload': {'id': str(i), 'name': f'Card {i}'}})() for i in range(800)]
    class Service:
        def search_cards(self, query, filters):
            calls.append(filters['limit'])
            return results[:filters['limit']]
    service = Service()
    monkeypatch.setattr(deck_import_service, '_build_card_service', lambda *a: service)
    monkeypatch.setattr(deck_import_service, '_build_card_candidates',
        lambda service, rows, source, **kwargs: list(rows))
    first = deck_import_service.search_scryfall_card_page('t:creature', page_size=250, local_only=True)
    second = deck_import_service.search_scryfall_card_page('t:creature', page_start=250,
                                                            page_size=250, local_only=True)
    assert calls == [251, 501]
    assert len(first.candidates) == len(second.candidates) == 250
    assert first.total_count == 251
    assert second.total_count == 501
    assert first.has_more is True
    assert second.has_more is True


def test_add_card_local_checkbox_and_text_without_image(tmp_path, monkeypatch):
    import dialogs
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    def no_network(*args, **kwargs):
        raise AssertionError('Local-only search or preview contacted the network')
    service = CardService(db_path=str(tmp_path / 'local-ui.sqlite3'),
                          fetch_json_fn=no_network, fetch_bytes_fn=no_network)
    service.database.upsert_card_payload(dict(id='local', oracle_id='oracle-local',
        name='Test Scholar', type_line='Creature', oracle_text='Draw a card.',
        colors=['U'], color_identity=['U'], cmc=2, set='test', collector_number='1',
        image_uris={'normal': 'https://example.invalid/image.png'}))
    monkeypatch.setattr(deck_import_service, '_build_card_service', lambda *a: service)
    monkeypatch.setattr(dialogs, 'get_default_card_service', lambda: service)
    monkeypatch.setattr(dialogs.high_res_service, 'fetch_preview_bytes', no_network)
    dialog = dialogs.AddCardDialog(None, str(tmp_path))
    monkeypatch.setattr(dialog, '_run_with_popup', lambda title, work: work())
    dialog._local_search_checkbox.setChecked(True)
    dialog._card_name_edit.setText('o:"draw a card"')
    dialog.refresh_card_results(reset_page=True)
    assert dialog._total_card_count == 1
    assert 'Draw a card.' in dialog._card_details_label.toPlainText()
    assert 'No local image' in dialog._card_preview_label.text()
    assert dialog._card_thumbnail_loader is None
    dialog.reject()
    dialog.deleteLater()
    app.processEvents()


def test_add_card_actions_stay_visible_with_large_preview(tmp_path):
    import dialogs
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    dialog = dialogs.AddCardDialog(None, str(tmp_path))
    dialog.resize(800, 600)
    dialog._card_preview_label.setPixmap(QPixmap(1000, 1400))
    dialog.show()
    app.processEvents()

    assert dialog._card_next_button.isVisible()
    assert dialog._card_cancel_button.isVisible()
    assert dialog._card_next_button.mapTo(dialog, dialog._card_next_button.rect().bottomRight()).y() < dialog.height()
    assert dialog._card_cancel_button.mapTo(dialog, dialog._card_cancel_button.rect().bottomRight()).y() < dialog.height()

    dialog.reject()
    dialog.deleteLater()
    app.processEvents()


def _runtime_dir(name: str) -> Path:
    target = Path(__file__).resolve().parents[1] / "projects" / ".codex_test_runtime" / f"{name}_{uuid.uuid4().hex}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def test_import_into_project_applies_cards_before_refresh(monkeypatch):
    seen_cards_during_refresh = []

    monkeypatch.setattr(
        deck_import,
        "import_decklist",
        lambda deck_text, image_dir, print_fn: deck_import.ImportResult(
            imported=[
                deck_import.ImportedCard(
                    entry=deck_import.DeckEntry(count=1, name="Plains"),
                    filename="scryfall_lea_232_plains.png",
                )
            ],
            unmatched_lines=[],
            failed_cards=[],
            backside_pairs={},
        ),
    )

    def fake_refresh(state, img_dict, print_fn, warn_fn=None):
        seen_cards_during_refresh.append(dict(state.cards))
        img_dict["scryfall_lea_232_plains.png"] = {"data": "b''", "size": (1, 1)}
        return state

    monkeypatch.setattr(
        deck_import_service.project_service,
        "refresh_after_image_changes",
        fake_refresh,
    )

    state = ProjectState()
    img_dict = {}

    result = deck_import_service.import_into_project(
        state,
        img_dict,
        "images",
        lambda _message: None,
        deck_text="1 Plains",
    )

    assert seen_cards_during_refresh == [{"scryfall_lea_232_plains.png": 1}]
    assert result.state.cards == {"scryfall_lea_232_plains.png": 1}
    assert "scryfall_lea_232_plains.png" in img_dict


def test_search_scryfall_card_page_filters_by_set_name(monkeypatch):
    calls = []

    def fake_fetch_json(url):
        calls.append(url)
        return {
            "object": "list",
            "data": [
                {
                    "id": "a",
                    "name": "Lightning Bolt",
                    "set": "lea",
                    "set_name": "Limited Edition Alpha",
                    "collector_number": "161",
                    "image_uris": {"small": "small-a", "normal": "normal-a"},
                },
                {
                    "id": "b",
                    "name": "Lightning Bolt",
                    "set": "m11",
                    "set_name": "Magic 2011",
                    "collector_number": "146",
                    "image_uris": {"small": "small-b", "normal": "normal-b"},
                },
            ],
            "has_more": False,
        }

    page = deck_import_service.search_scryfall_card_page(
        "Lightning Bolt",
        set_filter="alpha",
        fetch_json=fake_fetch_json,
    )

    assert len(page.candidates) == 1
    assert page.total_count == 1
    assert page.candidates[0].set_code == "lea"
    assert page.candidates[0].art_context.filename == "scryfall_lea_161_lightning-bolt.png"
    assert 'q=%28Lightning+Bolt%29+set%3Aalpha' in calls[0]


def test_search_scryfall_card_page_uses_broad_partial_name_query(monkeypatch):
    calls = []

    def fake_fetch_json(url):
        calls.append(url)
        return {
            "object": "list",
            "data": [
                {
                    "id": "bolt",
                    "name": "Lightning Bolt",
                    "set": "lea",
                    "set_name": "Limited Edition Alpha",
                    "collector_number": "161",
                    "image_uris": {"small": "small", "normal": "normal"},
                }
            ],
            "has_more": False,
        }

    page = deck_import_service.search_scryfall_card_page(
        "Bolt",
        fetch_json=fake_fetch_json,
    )

    assert len(page.candidates) == 1
    assert page.candidates[0].name == "Lightning Bolt"
    assert len(calls) == 1
    assert 'q=Bolt' in calls[0]
    assert '%21%22Bolt%22' not in calls[0]


def test_search_scryfall_card_page_uses_local_catalog_for_syntax_even_online(tmp_path, monkeypatch):
    def no_network(*args):
        raise AssertionError('Supported syntax must not contact Scryfall')
    service = CardService(db_path=str(tmp_path / 'syntax.sqlite3'),
                          fetch_json_fn=no_network, fetch_bytes_fn=no_network)
    service.database.upsert_card_payload(dict(
        id='spell', oracle_id='spell', name='Opt', type_line='Instant',
        oracle_text='Scry 1. Draw a card.', cmc=1, colors=['U'], color_identity=['U'],
        digital=False, set='dom', collector_number='60'))
    monkeypatch.setattr(deck_import_service, '_build_card_service', lambda *args: service)

    page = deck_import_service.search_scryfall_card_page(
        't:instant c:blue mv<=1 -is:digital', online_mode=True)

    assert [candidate.name for candidate in page.candidates] == ['Opt']
    assert page.search_source == 'local'


def test_detects_scryfall_operator_queries_but_not_plain_card_names():
    assert deck_import_service.is_scryfall_syntax_query("Lightning Bolt") is False
    assert deck_import_service.is_scryfall_syntax_query("oracle:draw c:u") is True
    assert deck_import_service.is_scryfall_syntax_query("pow>=5") is True


def test_search_scryfall_card_page_returns_empty_page_when_scryfall_has_no_matches(monkeypatch):
    calls = []

    def fake_fetch_json(url):
        calls.append(url)
        raise ValueError(
            "Your query didn't match any cards. Adjust your search terms or refer to the syntax guide at https://scryfall.com/docs/reference"
        )

    page = deck_import_service.search_scryfall_card_page(
        "Definitely Not A Real Card",
        fetch_json=fake_fetch_json,
        online_mode=True,
    )

    assert page.candidates == []
    assert page.total_count == 0
    assert page.search_source == "remote"
    assert len(calls) >= 1


def test_search_scryfall_card_page_raises_friendly_error_when_remote_unavailable_without_local(monkeypatch):
    def fake_fetch_json(_url):
        raise RemoteLookupUnavailable("offline")

    try:
        deck_import_service.search_scryfall_card_page(
            "Definitely Not A Real Card",
            fetch_json=fake_fetch_json,
            online_mode=True,
        )
    except ValueError as exc:
        assert "Connect to the internet" in str(exc)
    else:
        raise AssertionError("Expected offline search to raise a friendly error.")


def test_import_single_card_into_project_uses_default_art_and_refresh(monkeypatch):
    selected_card = deck_import_service.ScryfallCardCandidate(
        name="Plains",
        set_code="lea",
        set_name="Limited Edition Alpha",
        collector_number="232",
        card_id=None,
        oracle_id=None,
        scryfall_id="card-1",
        preview_url="preview",
        thumbnail_url="thumb",
        filename="scryfall_lea_232_plains.png",
        art_context=high_res.CardContext(
            filename="scryfall_lea_232_plains.png",
            query="Plains",
            display_name="Plains",
            set_code="lea",
            collector_number="232",
        ),
        card_data={},
    )

    monkeypatch.setattr(
        deck_import,
        "resolve_card",
        lambda entry, fetch_json, card_service=None: {
            "name": entry.name,
            "set": entry.set_code,
            "collector_number": entry.collector_number,
            "image_uris": {"png": "https://img.test/plains.png"},
        },
    )
    monkeypatch.setattr(
        deck_import,
        "download_card_image_set",
        lambda card_data, entry, image_dir, print_fn, fetch_bytes, card_service=None: (
            deck_import.ImportedCard(entry=entry, filename="scryfall_lea_232_plains.png"),
            None,
        ),
    )

    refresh_calls = []

    def fake_refresh(state, img_dict, print_fn, warn_fn=None):
        refresh_calls.append(dict(state.cards))
        img_dict["scryfall_lea_232_plains.png"] = {"data": "b''", "size": (1, 1)}
        return state

    monkeypatch.setattr(
        deck_import_service.project_service,
        "refresh_after_image_changes",
        fake_refresh,
    )

    applied_art_calls = []
    monkeypatch.setattr(
        deck_import_service.high_res_service,
        "apply_candidate_to_project",
        lambda *args, **kwargs: applied_art_calls.append((args, kwargs)),
    )

    state = ProjectState()
    img_dict = {}
    result = deck_import_service.import_single_card_into_project(
        state,
        img_dict,
        "images",
        selected_card,
        lambda _message: None,
    )

    assert result.filename == "scryfall_lea_232_plains.png"
    assert result.backside_filename is None
    assert state.cards == {"scryfall_lea_232_plains.png": 1}
    assert state.get_card_metadata("scryfall_lea_232_plains.png") == {
        "name": "Plains",
        "set_code": "lea",
        "collector_number": "232",
    }
    assert refresh_calls == [{"scryfall_lea_232_plains.png": 1}]
    assert applied_art_calls == []

    deck_import_service.import_single_card_into_project(
        state, img_dict, "images", selected_card, lambda _message: None,
    )
    assert state.get_card_count(result.filename) == 2


def test_import_single_card_into_project_applies_optional_art_and_backside(monkeypatch):
    selected_card = deck_import_service.ScryfallCardCandidate(
        name="Fable of the Mirror-Breaker // Reflection of Kiki-Jiki",
        set_code="neo",
        set_name="Kamigawa: Neon Dynasty",
        collector_number="141",
        card_id=None,
        oracle_id=None,
        scryfall_id="card-2",
        preview_url="preview",
        thumbnail_url="thumb",
        filename="scryfall_neo_141_fable-of-the-mirror-breaker.png",
        art_context=high_res.CardContext(
            filename="scryfall_neo_141_fable-of-the-mirror-breaker.png",
            query="Fable of the Mirror-Breaker // Reflection of Kiki-Jiki",
            display_name="Fable of the Mirror-Breaker // Reflection of Kiki-Jiki",
            set_code="neo",
            collector_number="141",
        ),
        card_data={},
    )
    art_candidate = high_res.HighResCandidate(
        identifier="art-1",
        name=selected_card.name,
        dpi=600,
        extension="png",
        download_link="https://art.test/front.png",
        small_thumbnail_url="thumb",
        medium_thumbnail_url="preview",
        source_id=1,
        source_name="MPCFill",
        art_source="mpcfill",
    )

    monkeypatch.setattr(
        deck_import,
        "resolve_card",
        lambda entry, fetch_json, card_service=None: {
            "name": entry.name,
            "set": entry.set_code,
            "collector_number": entry.collector_number,
            "card_faces": [
                {"name": "Fable of the Mirror-Breaker", "image_uris": {"png": "front"}},
                {"name": "Reflection of Kiki-Jiki", "image_uris": {"png": "back"}},
            ],
        },
    )
    monkeypatch.setattr(
        deck_import,
        "download_card_image_set",
        lambda card_data, entry, image_dir, print_fn, fetch_bytes, card_service=None: (
            deck_import.ImportedCard(
                entry=entry,
                filename="scryfall_neo_141_fable-of-the-mirror-breaker.png",
            ),
            "__scryfall_neo_141_reflection-of-kiki-jiki.png",
        ),
    )

    refresh_calls = []
    monkeypatch.setattr(
        deck_import_service.project_service,
        "refresh_after_image_changes",
        lambda state, img_dict, print_fn, warn_fn=None: refresh_calls.append(dict(state.cards)) or state,
    )

    applied_art_calls = []
    monkeypatch.setattr(
        deck_import_service.high_res_service,
        "apply_candidate_to_project",
        lambda state, img_dict, card_name, candidate, source, backend_url, print_fn, warn_fn=None: applied_art_calls.append(
            (card_name, candidate.identifier, source, backend_url)
        ),
    )

    state = ProjectState()
    result = deck_import_service.import_single_card_into_project(
        state,
        {},
        "images",
        selected_card,
        lambda _message: None,
        art_candidate=art_candidate,
        art_source="mpcfill",
        backend_url="https://mpcfill.test/",
    )

    assert result.filename == "scryfall_neo_141_fable-of-the-mirror-breaker.png"
    assert result.backside_filename == "__scryfall_neo_141_reflection-of-kiki-jiki.png"
    assert state.cards["scryfall_neo_141_fable-of-the-mirror-breaker.png"] == 1
    assert state.backsides == {
        "scryfall_neo_141_fable-of-the-mirror-breaker.png": "__scryfall_neo_141_reflection-of-kiki-jiki.png"
    }
    assert refresh_calls == [{"scryfall_neo_141_fable-of-the-mirror-breaker.png": 1}]
    assert applied_art_calls == [
        (
            "scryfall_neo_141_fable-of-the-mirror-breaker.png",
            "art-1",
            "mpcfill",
            "https://mpcfill.test/",
        )
    ]


def test_search_scryfall_card_page_uses_local_results_when_offline(monkeypatch):
    runtime_dir = _runtime_dir("offline_search")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
    )
    payload = {
        "id": "card-opt",
        "oracle_id": "oracle-opt",
        "name": "Opt",
        "set": "eld",
        "set_name": "Throne of Eldraine",
        "collector_number": "59",
        "image_uris": {
            "png": "https://img.test/opt.png",
            "normal": "https://img.test/opt-normal.png",
            "small": "https://img.test/opt-small.png",
        },
    }
    service.database.upsert_card_payload(payload)
    asset_id = service.store_image_bytes(
        b"png-bytes",
        extension="png",
        source="scryfall",
        source_url=payload["image_uris"]["png"],
    )
    service.set_print_image_asset("card-opt", asset_id, preferred_name="scryfall_eld_59_opt.png")
    monkeypatch.setattr(deck_import_service, "_build_card_service", lambda fetch_json=None: service)

    page = deck_import_service.search_scryfall_card_page("Opt", online_mode=False)

    assert page.search_source == "local"
    assert len(page.candidates) == 1
    assert page.candidates[0].card_id == "card-opt"
    assert page.candidates[0].image_asset_id == asset_id
    assert page.candidates[0].local_image_path is not None


def test_search_scryfall_card_page_prefers_local_results_when_online_mode_off(monkeypatch):
    runtime_dir = _runtime_dir("merged_search")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: {
            "object": "list",
            "data": [
                {
                    "id": "card-opt-local",
                    "oracle_id": "oracle-opt",
                    "name": "Opt",
                    "set": "eld",
                    "set_name": "Throne of Eldraine",
                    "collector_number": "59",
                    "image_uris": {"small": "small-local", "normal": "normal-local", "png": "png-local"},
                },
                {
                    "id": "card-opt-remote",
                    "oracle_id": "oracle-opt",
                    "name": "Opt",
                    "set": "dom",
                    "set_name": "Dominaria",
                    "collector_number": "60",
                    "image_uris": {"small": "small-remote", "normal": "normal-remote", "png": "png-remote"},
                },
            ],
            "has_more": False,
        },
    )
    service.database.upsert_card_payload(
        {
            "id": "card-opt-local",
            "oracle_id": "oracle-opt",
            "name": "Opt",
            "set": "eld",
            "set_name": "Throne of Eldraine",
            "collector_number": "59",
            "image_uris": {"small": "small-local", "normal": "normal-local", "png": "png-local"},
        }
    )
    monkeypatch.setattr(deck_import_service, "_build_card_service", lambda fetch_json=None: service)

    page = deck_import_service.search_scryfall_card_page("Opt", online_mode=False)

    assert page.search_source == "local"
    assert [candidate.card_id for candidate in page.candidates] == ["card-opt-local"]


def test_search_scryfall_card_page_online_mode_still_prefers_local_catalog(monkeypatch):
    runtime_dir = _runtime_dir("online_default_search")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: {
            "object": "list",
            "data": [
                {
                    "id": "card-opt-remote",
                    "oracle_id": "oracle-opt-remote",
                    "name": "Opt",
                    "set": "dom",
                    "set_name": "Dominaria",
                    "collector_number": "60",
                    "image_uris": {"small": "small-remote", "normal": "normal-remote", "png": "png-remote"},
                },
            ],
            "has_more": False,
        },
    )
    service.database.upsert_card_payload(
        {
            "id": "card-opt-local",
            "oracle_id": "oracle-opt-local",
            "name": "Opt",
            "set": "eld",
            "set_name": "Throne of Eldraine",
            "collector_number": "59",
            "image_uris": {"small": "small-local", "normal": "normal-local", "png": "png-local"},
        }
    )
    monkeypatch.setattr(deck_import_service.CFG, "OnlineMode", True)
    monkeypatch.setattr(deck_import_service.CFG, "HighResCacheTTLSeconds", 60)
    monkeypatch.setattr(deck_import_service, "_build_card_service", lambda fetch_json=None: service)

    page = deck_import_service.search_scryfall_card_page("Opt")
    cached = deck_import_service.search_scryfall_card_page("Opt")

    assert page.search_source == "local"
    assert [candidate.card_id for candidate in page.candidates] == ["card-opt-local"]
    assert [candidate.card_id for candidate in cached.candidates] == ["card-opt-local"]


def test_search_scryfall_card_page_short_query_uses_scryfall_partial_search(monkeypatch):
    runtime_dir = _runtime_dir("short_local_search")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: {
            "object": "list",
            "data": [{
                "id": "aang",
                "oracle_id": "oracle-aang",
                "name": "Aang, Air Nomad",
                "set": "tle",
                "set_name": "Avatar",
                "collector_number": "210",
                "image_uris": {"small": "small-aang", "normal": "normal-aang"},
            }],
            "has_more": False,
        },
    )
    for payload in [
        {
            "id": "aang",
            "oracle_id": "oracle-aang",
            "name": "Aang, Air Nomad",
            "set": "tle",
            "set_name": "Avatar",
            "collector_number": "210",
            "image_uris": {"small": "small-aang", "normal": "normal-aang", "png": "png-aang"},
        },
        {
            "id": "ach",
            "oracle_id": "oracle-ach",
            "name": '"Ach! Hans, Run!"',
            "set": "unh",
            "set_name": "Unhinged",
            "collector_number": "116",
            "image_uris": {"small": "small-ach", "normal": "normal-ach", "png": "png-ach"},
        },
    ]:
        service.database.upsert_card_payload(payload)
    monkeypatch.setattr(deck_import_service, "_build_card_service", lambda fetch_json=None: service)

    page = deck_import_service.search_scryfall_card_page("a", online_mode=False)

    assert page.search_source == "local"
    assert {candidate.card_id for candidate in page.candidates} == {"aang", "ach"}


def test_search_scryfall_card_page_returns_aang_catalog_matches(monkeypatch):
    runtime_dir = _runtime_dir("aang_search")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
    )
    service.database.upsert_card_payload(
        {
            "id": "aang",
            "oracle_id": "oracle-aang",
            "name": "Aang, Air Nomad",
            "set": "tle",
            "set_name": "Avatar",
            "collector_number": "210",
            "image_uris": {"small": "small-aang", "normal": "normal-aang", "png": "png-aang"},
        }
    )
    monkeypatch.setattr(deck_import_service, "_build_card_service", lambda fetch_json=None: service)

    page = deck_import_service.search_scryfall_card_page("aang")

    assert [candidate.name for candidate in page.candidates] == ["Aang, Air Nomad"]


def test_search_scryfall_card_page_keeps_local_results_when_remote_no_match_errors(monkeypatch):
    runtime_dir = _runtime_dir("remote_no_match_keeps_local")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: (_ for _ in ()).throw(
            ValueError(
                "Your query didn't match any cards. Adjust your search terms or refer to the syntax guide at https://scryfall.com/docs/reference"
            )
        ),
    )
    service.database.upsert_card_payload(
        {
            "id": "plains",
            "oracle_id": "oracle-plains",
            "name": "Plains",
            "set": "lea",
            "set_name": "Limited Edition Alpha",
            "collector_number": "286",
            "image_uris": {"small": "small-plains", "normal": "normal-plains", "png": "png-plains"},
        }
    )
    monkeypatch.setattr(deck_import_service, "_build_card_service", lambda fetch_json=None: service)

    page = deck_import_service.search_scryfall_card_page("pla", online_mode=False)

    assert page.search_source == "local"
    assert [candidate.name for candidate in page.candidates] == ["Plains"]


def test_import_single_card_into_project_uses_local_card_and_asset_when_available(monkeypatch):
    runtime_dir = _runtime_dir("local_single_card")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
    )
    payload = {
        "id": "card-plains",
        "oracle_id": "oracle-plains",
        "name": "Plains",
        "set": "lea",
        "set_name": "Limited Edition Alpha",
        "collector_number": "232",
        "image_uris": {
            "png": "https://img.test/plains.png",
            "normal": "https://img.test/plains-normal.png",
            "small": "https://img.test/plains-small.png",
        },
    }
    service.database.upsert_card_payload(payload)
    asset_id = service.store_image_bytes(
        b"png-bytes",
        extension="png",
        source="scryfall",
        source_url=payload["image_uris"]["png"],
    )
    service.set_print_image_asset("card-plains", asset_id, preferred_name="scryfall_lea_232_plains.png")
    monkeypatch.setattr(deck_import_service, "_build_card_service", lambda fetch_json=None: service)
    monkeypatch.setattr(
        deck_import,
        "resolve_card",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("resolve_card should not be called")),
    )
    monkeypatch.setattr(
        deck_import,
        "download_card_image_set",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("download_card_image_set should not be called")),
    )
    monkeypatch.setattr(
        deck_import_service.project_service,
        "refresh_after_image_changes",
        lambda state, img_dict, print_fn, warn_fn=None: state,
    )

    selected_card = deck_import_service.ScryfallCardCandidate(
        name="Plains",
        set_code="lea",
        set_name="Limited Edition Alpha",
        collector_number="232",
        card_id="card-plains",
        oracle_id="oracle-plains",
        scryfall_id="card-plains",
        preview_url="preview",
        thumbnail_url="thumb",
        filename="scryfall_lea_232_plains.png",
        art_context=high_res.CardContext(
            filename="scryfall_lea_232_plains.png",
            query="Plains",
            display_name="Plains",
            set_code="lea",
            collector_number="232",
        ),
        card_data=payload,
        image_asset_id=asset_id,
        local_image_path=service.get_image_path("card-plains"),
        search_source="local",
    )

    state = ProjectState()
    result = deck_import_service.import_single_card_into_project(
        state,
        {},
        "images",
        selected_card,
        lambda _message: None,
    )

    assert result.filename == "scryfall_lea_232_plains.png"
    assert state.get_card_entry("scryfall_lea_232_plains.png").image_asset_id == asset_id


def test_import_single_card_promotes_online_cache_row_and_saves_image(monkeypatch):
    runtime_dir = _runtime_dir("online_import_promotes")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: (_ for _ in ()).throw(AssertionError("card data is already selected")),
    )
    payload = {
        "id": "card-opt",
        "oracle_id": "oracle-opt",
        "name": "Opt",
        "set": "dom",
        "set_name": "Dominaria",
        "collector_number": "60",
        "image_uris": {
            "png": "https://img.test/opt.png",
            "normal": "https://img.test/opt-normal.png",
            "small": "https://img.test/opt-small.png",
        },
    }
    service.database.upsert_card_payload(
        payload,
        cache_scope="online_search",
        cache_expires_at=9999999999,
    )
    monkeypatch.setattr(deck_import_service, "_build_card_service", lambda fetch_json=None: service)
    monkeypatch.setattr(
        deck_import_service.project_service,
        "refresh_after_image_changes",
        lambda state, img_dict, print_fn, warn_fn=None: state,
    )
    selected_card = deck_import_service.ScryfallCardCandidate(
        name="Opt",
        set_code="dom",
        set_name="Dominaria",
        collector_number="60",
        card_id="card-opt",
        oracle_id="oracle-opt",
        scryfall_id="card-opt",
        preview_url="https://img.test/opt-normal.png",
        thumbnail_url="https://img.test/opt-small.png",
        filename="scryfall_dom_60_opt.png",
        art_context=high_res.CardContext(
            filename="scryfall_dom_60_opt.png",
            query="Opt",
            display_name="Opt",
            set_code="dom",
            collector_number="60",
        ),
        card_data=payload,
        search_source="remote",
    )

    state = ProjectState(image_dir=str(runtime_dir / "project_images"), img_cache=str(runtime_dir / "img.cache"))
    result = deck_import_service.import_single_card_into_project(
        state,
        {},
        state.image_dir,
        selected_card,
        lambda _message: None,
        fetch_bytes=lambda _url: b"png-bytes",
    )

    entry = state.get_card_entry("scryfall_dom_60_opt.png")
    with service.database.connect() as connection:
        row = connection.execute(
            "SELECT cache_scope, cache_expires_at FROM prints WHERE card_id = ?",
            ("card-opt",),
        ).fetchone()

    assert result.filename == "scryfall_dom_60_opt.png"
    assert entry is not None
    assert entry.image_asset_id is not None
    assert row["cache_scope"] is None
    assert row["cache_expires_at"] is None
    assert (runtime_dir / "project_images" / "scryfall_dom_60_opt.png").exists()
