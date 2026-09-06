import deck_import
import logging
from mtg_core import CardService, RemoteLookupUnavailable


def test_parse_decklist_aggregates_duplicate_lines_and_skips_sections():
    deck_text = """
Deck
4 Lightning Bolt
2 Lightning Bolt
Commander
1 Atraxa, Praetors' Voice
"""

    entries, unmatched = deck_import.parse_decklist(deck_text)

    assert unmatched == []
    assert entries == [
        deck_import.DeckEntry(count=6, name="Lightning Bolt"),
        deck_import.DeckEntry(count=1, name="Atraxa, Praetors' Voice"),
    ]


def test_parse_decklist_supports_set_code_and_collector_number():
    entries, unmatched = deck_import.parse_decklist("1 Opt (eld) 59\n")

    assert unmatched == []
    assert entries == [
        deck_import.DeckEntry(
            count=1,
            name="Opt",
            set_code="eld",
            collector_number="59",
        )
    ]


def test_parse_decklist_supports_hyphenated_collector_number():
    entries, unmatched = deck_import.parse_decklist(
        "1 Horned Sliver (plst) TMP-234\n"
    )

    assert unmatched == []
    assert entries == [
        deck_import.DeckEntry(
            count=1,
            name="Horned Sliver",
            set_code="plst",
            collector_number="TMP-234",
        )
    ]


def test_parse_decklist_collects_unmatched_lines():
    entries, unmatched = deck_import.parse_decklist("123\n2 Fire // Ice\n")

    assert entries == [deck_import.DeckEntry(count=2, name="Fire // Ice")]
    assert unmatched == ["123"]


def test_card_names_without_quantities_mix_with_counts_and_printings():
    entries, unmatched = deck_import.parse_decklist(
        "Commander\nAtraxa, Praetors' Voice\nSol Ring\n2 Sol Ring\n"
        "sol ring\nSB: Opt (eld) 59\nFire // Ice\n# comment\n// comment\n")
    assert unmatched == []
    assert entries == [
        deck_import.DeckEntry(1, "Atraxa, Praetors' Voice"),
        deck_import.DeckEntry(4, 'Sol Ring'),
        deck_import.DeckEntry(1, 'Opt', 'eld', '59'),
        deck_import.DeckEntry(1, 'Fire // Ice'),
    ]


def test_parse_decklist_supports_csv_with_exact_printing_fields():
    deck_text = (
        "section,count,name,set,set_code,collector_number,lang\n"
        "nonlands,1,Acclaimed Contender,March of the Machine Commander,moc,166,en\n"
        "lands,2,Godless Shrine,Edge of Eternities,eoe,254,en\n"
    )

    entries, unmatched = deck_import.parse_decklist(deck_text)

    assert unmatched == []
    assert entries == [
        deck_import.DeckEntry(count=1, name="Acclaimed Contender", set_code="moc", collector_number="166"),
        deck_import.DeckEntry(count=2, name="Godless Shrine", set_code="eoe", collector_number="254"),
    ]


def test_parse_decklist_csv_aggregates_duplicates_by_exact_printing():
    deck_text = (
        "count,name,set_code,collector_number\n"
        "1,Dauntless Bodyguard,plst,DOM-14\n"
        "2,Dauntless Bodyguard,plst,DOM-14\n"
        "1,Dauntless Bodyguard,dom,14\n"
    )

    entries, unmatched = deck_import.parse_decklist(deck_text)

    assert unmatched == []
    assert entries == [
        deck_import.DeckEntry(count=3, name="Dauntless Bodyguard", set_code="plst", collector_number="DOM-14"),
        deck_import.DeckEntry(count=1, name="Dauntless Bodyguard", set_code="dom", collector_number="14"),
    ]


def test_parse_decklist_csv_reports_malformed_rows():
    deck_text = (
        "count,name,set_code,collector_number\n"
        "1,Acclaimed Contender,moc,166\n"
        "1,Bad Row,moc,\n"
    )

    entries, unmatched = deck_import.parse_decklist(deck_text)

    assert entries == [
        deck_import.DeckEntry(count=1, name="Acclaimed Contender", set_code="moc", collector_number="166"),
    ]
    assert unmatched == ["CSV row 3"]


def test_import_decklist_downloads_images_and_applies_counts(tmp_path):
    def fake_fetch_json(url):
        if "named" in url:
            return {
                "name": "Lightning Bolt",
                "set": "clu",
                "collector_number": "141",
                "image_uris": {"png": "https://img/lightning-bolt.png"},
            }
        raise AssertionError(f"Unexpected URL: {url}")

    def fake_fetch_bytes(url):
        assert url == "https://img/lightning-bolt.png"
        return b"png-bytes"

    result = deck_import.import_decklist(
        "4 Lightning Bolt\n",
        str(tmp_path),
        fetch_json=fake_fetch_json,
        fetch_bytes=fake_fetch_bytes,
    )

    assert result.unmatched_lines == []
    assert result.failed_cards == []
    assert result.backside_pairs == {}
    assert [card.filename for card in result.imported] == [
        "scryfall_clu_141_lightning-bolt.png"
    ]
    assert (tmp_path / "scryfall_clu_141_lightning-bolt.png").read_bytes() == b"png-bytes"

    print_dict = {"cards": {}}
    deck_import.apply_imported_counts(print_dict, result.imported)
    assert print_dict["cards"] == {"scryfall_clu_141_lightning-bolt.png": 4}


def test_import_decklist_reports_partial_failures(tmp_path):
    def fake_fetch_json(url):
        if "named" in url and "Lightning+Bolt" in url:
            return {
                "name": "Lightning Bolt",
                "set": "clu",
                "collector_number": "141",
                "image_uris": {"png": "https://img/lightning-bolt.png"},
            }
        raise ValueError("not found")

    result = deck_import.import_decklist(
        "4 Lightning Bolt\n2 Missing Card\n",
        str(tmp_path),
        fetch_json=fake_fetch_json,
        fetch_bytes=lambda _url: b"image",
    )

    assert [card.filename for card in result.imported] == [
        "scryfall_clu_141_lightning-bolt.png"
    ]
    assert result.failed_cards == ["Missing Card"]
    assert result.backside_pairs == {}


def test_import_decklist_logs_recoverable_entry_failure(tmp_path, caplog):
    def fake_fetch_json(_url):
        raise OSError("network down")

    with caplog.at_level(logging.ERROR):
        result = deck_import.import_decklist(
            "1 Lightning Bolt\n",
            str(tmp_path),
            fetch_json=fake_fetch_json,
            fetch_bytes=lambda _url: b"image",
        )

    assert result.imported == []
    assert result.failed_cards == ["Lightning Bolt"]
    assert "operation=import_entry" in caplog.text
    assert "Lightning Bolt" in caplog.text


def test_import_decklist_csv_uses_exact_printing_endpoint(tmp_path):
    seen_urls = []

    def fake_fetch_json(url):
        seen_urls.append(url)
        return {
            "name": "Acclaimed Contender",
            "set": "moc",
            "collector_number": "166",
            "image_uris": {"png": "https://img/acclaimed-contender.png"},
        }

    result = deck_import.import_decklist(
        "count,name,set_code,collector_number\n1,Acclaimed Contender,moc,166\n",
        str(tmp_path),
        fetch_json=fake_fetch_json,
        fetch_bytes=lambda _url: b"image",
    )

    assert seen_urls == ["https://api.scryfall.com/cards/moc/166"]
    assert result.unmatched_lines == []
    assert result.failed_cards == []
    assert result.backside_pairs == {}
    assert [card.filename for card in result.imported] == [
        "scryfall_moc_166_acclaimed-contender.png"
    ]


def test_import_decklist_normalizes_lowercase_plst_collector_prefix(tmp_path):
    seen_urls = []

    def fake_fetch_json(url):
        seen_urls.append(url)
        return {
            "name": "Horned Sliver",
            "set": "plst",
            "collector_number": "TMP-234",
            "image_uris": {"png": "https://img/horned-sliver.png"},
        }

    result = deck_import.import_decklist(
        "1 Horned Sliver (plst) tmp-234\n",
        str(tmp_path),
        fetch_json=fake_fetch_json,
        fetch_bytes=lambda _url: b"image",
    )

    assert seen_urls == ["https://api.scryfall.com/cards/plst/TMP-234"]
    assert result.failed_cards == []


def test_is_archidekt_url_validates_public_deck_links():
    assert deck_import.is_archidekt_url("https://archidekt.com/decks/12345/test-deck")
    assert deck_import.is_archidekt_url("https://www.archidekt.com/decks/12345")
    assert not deck_import.is_archidekt_url("https://moxfield.com/decks/12345")
    assert not deck_import.is_archidekt_url("not a url")


def test_supported_deck_url_accepts_all_public_deck_providers():
    assert deck_import.is_supported_deck_url("https://archidekt.com/decks/12345/test-deck")
    assert deck_import.is_supported_deck_url("https://www.moxfield.com/decks/abc_DEF-123")
    assert deck_import.is_supported_deck_url("https://blueprintmtg.io/decks/KamizObscu-123")
    assert not deck_import.is_supported_deck_url("https://example.com/decks/123")


def test_parse_moxfield_json_reads_all_boards_and_exact_printings():
    entries = deck_import.parse_moxfield_json({
        "mainboard": {"a": {"quantity": 2, "card": {
            "name": "Lightning Bolt", "setCode": "clu", "collectorNumber": "141"
        }}},
        "commanders": {"b": {"quantity": 1, "card": {
            "name": "Atraxa, Praetors' Voice", "set": "2xm", "number": "190"
        }}},
        "sideboard": {"c": {"quantity": 1, "card": {"name": "Opt"}}},
    })

    assert entries == [
        deck_import.DeckEntry(2, "Lightning Bolt", "clu", "141"),
        deck_import.DeckEntry(1, "Opt"),
        deck_import.DeckEntry(1, "Atraxa, Praetors' Voice", "2xm", "190"),
    ]


def test_parse_blueprint_json_reads_saved_deck_payload():
    entries = deck_import.parse_blueprint_json([{
        "visibility": "public",
        "payload": {
            "deck": [{"count": 2, "card": {
                "name": "Sol Ring", "set": "ltc", "collector_number": "263"
            }}],
            "considering": [{"count": 1, "card": {"name": "Arcane Signet"}}],
        },
    }])

    assert entries == [
        deck_import.DeckEntry(2, "Sol Ring", "ltc", "263"),
        deck_import.DeckEntry(1, "Arcane Signet"),
    ]


def test_parse_archidekt_html_extracts_entries_and_aggregates_duplicates():
    html = """
<html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"redux":{"deck":{"cardMap":{
  "a":{"name":"Lightning Bolt","qty":2,"setCode":"clu","collectorNumber":"141"},
  "b":{"name":"Lightning Bolt","qty":1,"setCode":"clu","collectorNumber":"141"},
  "c":{"name":"Opt","qty":1,"setCode":"eld","collectorNumber":"59"}
}}}}}}
</script>
</body></html>
"""

    entries = deck_import.parse_archidekt_html(html)

    assert entries == [
        deck_import.DeckEntry(count=3, name="Lightning Bolt", set_code="clu", collector_number="141"),
        deck_import.DeckEntry(count=1, name="Opt", set_code="eld", collector_number="59"),
    ]


def test_parse_archidekt_html_accepts_extra_script_attributes():
    html = """
<html><body>
<script nonce="abc123" type="application/json" id="__NEXT_DATA__" crossorigin="anonymous">
{"props":{"pageProps":{"redux":{"deck":{"cardMap":{
  "a":{"name":"Lightning Bolt","qty":1,"setCode":"clu","collectorNumber":"141"}
}}}}}}
</script>
</body></html>
"""

    entries = deck_import.parse_archidekt_html(html)

    assert entries == [
        deck_import.DeckEntry(count=1, name="Lightning Bolt", set_code="clu", collector_number="141"),
    ]


def test_parse_archidekt_html_rejects_missing_deck_data():
    try:
        deck_import.parse_archidekt_html("<html><body>No deck here</body></html>")
    except ValueError as exc:
        assert "did not include deck data" in str(exc)
    else:
        raise AssertionError("Expected parse_archidekt_html to fail")


def test_import_archidekt_url_uses_exact_printing_endpoints(tmp_path):
    seen_urls = []

    def fake_fetch_text(url):
        assert url == "https://archidekt.com/decks/12345/test-deck"
        return """
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"redux":{"deck":{"cardMap":{
  "a":{"name":"Lightning Bolt","qty":2,"setCode":"clu","collectorNumber":"141"},
  "b":{"name":"Opt","qty":1,"setCode":"eld","collectorNumber":"59"}
}}}}}}
</script>
"""

    def fake_fetch_json(url):
        seen_urls.append(url)
        if url.endswith("/clu/141"):
            return {
                "name": "Lightning Bolt",
                "set": "clu",
                "collector_number": "141",
                "image_uris": {"png": "https://img/lightning-bolt.png"},
            }
        if url.endswith("/eld/59"):
            return {
                "name": "Opt",
                "set": "eld",
                "collector_number": "59",
                "image_uris": {"png": "https://img/opt.png"},
            }
        raise AssertionError(f"Unexpected URL: {url}")

    result = deck_import.import_archidekt_url(
        "https://archidekt.com/decks/12345/test-deck",
        str(tmp_path),
        fetch_text=fake_fetch_text,
        fetch_json=fake_fetch_json,
        fetch_bytes=lambda url: b"image:" + url.encode("utf-8"),
    )

    assert seen_urls == [
        "https://api.scryfall.com/cards/clu/141",
        "https://api.scryfall.com/cards/eld/59",
    ]
    assert result.unmatched_lines == []
    assert result.failed_cards == []
    assert result.backside_pairs == {}
    assert result.imported_count == 3


def test_import_archidekt_url_rejects_invalid_url(tmp_path):
    try:
        deck_import.import_archidekt_url("https://example.com/not-archidekt", str(tmp_path))
    except ValueError as exc:
        assert "not a valid public Archidekt deck link" in str(exc)
    else:
        raise AssertionError("Expected import_archidekt_url to fail")


def test_import_decklist_downloads_double_faced_card_and_assigns_backside(tmp_path):
    def fake_fetch_json(url):
        assert "named" in url
        return {
            "name": "Invasion of New Phyrexia // Teferi Akosa of Zhalfir",
            "set": "mom",
            "collector_number": "239",
            "card_faces": [
                {
                    "name": "Invasion of New Phyrexia",
                    "image_uris": {"png": "https://img/front.png"},
                },
                {
                    "name": "Teferi Akosa of Zhalfir",
                    "image_uris": {"png": "https://img/back.png"},
                },
            ],
        }

    result = deck_import.import_decklist(
        "1 Invasion of New Phyrexia\n",
        str(tmp_path),
        fetch_json=fake_fetch_json,
        fetch_bytes=lambda url: url.encode("utf-8"),
    )

    assert result.failed_cards == []
    assert [card.filename for card in result.imported] == [
        "scryfall_mom_239_invasion-of-new-phyrexia.png"
    ]
    assert result.backside_pairs == {
        "scryfall_mom_239_invasion-of-new-phyrexia.png": "__scryfall_mom_239_teferi-akosa-of-zhalfir.png"
    }
    assert (tmp_path / "scryfall_mom_239_invasion-of-new-phyrexia.png").read_bytes() == b"https://img/front.png"
    assert (tmp_path / "__scryfall_mom_239_teferi-akosa-of-zhalfir.png").read_bytes() == b"https://img/back.png"


def test_import_decklist_uses_local_db_assets_when_offline(tmp_path, monkeypatch):
    service = CardService(
        db_path=str(tmp_path / "card_data.sqlite3"),
        image_root=str(tmp_path / "images_db"),
        fetch_json_fn=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
        fetch_bytes_fn=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
    )
    payload = {
        "id": "card-bolt",
        "oracle_id": "oracle-bolt",
        "name": "Lightning Bolt",
        "set": "clu",
        "set_name": "Ravnica: Clue Edition",
        "collector_number": "141",
        "image_uris": {
            "png": "https://img/lightning-bolt.png",
            "normal": "https://img/lightning-bolt-normal.png",
            "small": "https://img/lightning-bolt-small.png",
        },
    }
    service.database.upsert_card_payload(payload)
    asset_id = service.store_image_bytes(
        b"png-bytes",
        extension="png",
        source="scryfall",
        source_url=payload["image_uris"]["png"],
    )
    service.set_print_image_asset("card-bolt", asset_id, preferred_name="scryfall_clu_141_lightning-bolt.png")
    monkeypatch.setattr(deck_import, "_build_card_service", lambda fetch_json=None: service)

    result = deck_import.import_decklist(
        "4 Lightning Bolt\n",
        str(tmp_path / "project_images"),
        fetch_json=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
        fetch_bytes=lambda _url: (_ for _ in ()).throw(AssertionError("fetch_bytes should not be called")),
    )

    assert result.failed_cards == []
    assert [card.filename for card in result.imported] == ["scryfall_clu_141_lightning-bolt.png"]
    assert result.imported[0].image_asset_id == asset_id


def test_import_decklist_reports_offline_miss_without_raw_network_error(tmp_path):
    result = deck_import.import_decklist(
        "1 Missing Card\n",
        str(tmp_path),
        fetch_json=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
        fetch_bytes=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
    )

    assert result.imported == []
    assert result.failed_cards == ["Missing Card"]


def test_apply_import_result_sets_backsides_and_enables_backside_mode():
    result = deck_import.ImportResult(
        imported=[
            deck_import.ImportedCard(
                entry=deck_import.DeckEntry(count=2, name="Invasion of New Phyrexia"),
                filename="scryfall_mom_239_invasion-of-new-phyrexia.png",
            )
        ],
        unmatched_lines=[],
        failed_cards=[],
        backside_pairs={
            "scryfall_mom_239_invasion-of-new-phyrexia.png": "__scryfall_mom_239_teferi-akosa-of-zhalfir.png"
        },
    )
    print_dict = {
        "cards": {},
        "backsides": {},
        "backside_enabled": False,
    }

    deck_import.apply_import_result(print_dict, result)

    assert print_dict["cards"] == {
        "scryfall_mom_239_invasion-of-new-phyrexia.png": 2
    }
    assert print_dict["backsides"] == {
        "scryfall_mom_239_invasion-of-new-phyrexia.png": "__scryfall_mom_239_teferi-akosa-of-zhalfir.png"
    }
    assert print_dict["backside_enabled"] is True
    assert print_dict["card_metadata"] == {
        "scryfall_mom_239_invasion-of-new-phyrexia.png": {
            "name": "Invasion of New Phyrexia",
            "set_code": None,
            "collector_number": None,
        }
    }
