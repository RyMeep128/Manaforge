from __future__ import annotations

import uuid
from pathlib import Path

from mtg_core import RemoteLookupUnavailable
from mtg_core.db import default_db_path
from mtg_core.paths import core_data_root, data_root
from mtg_core.services import CardService
from mtg_core.sync import build_print_search_url, search_prints_payloads


def _workspace_runtime_dir(name: str) -> Path:
    base = Path.cwd() / "Mtg_Projects" / "mtg_proxy" / "projects" / ".codex_test_runtime"
    base.mkdir(parents=True, exist_ok=True)
    target = base / f"{name}_{uuid.uuid4().hex}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _sample_print(
    *,
    card_id: str,
    oracle_id: str,
    name: str,
    set_code: str,
    set_name: str,
    collector_number: str,
    released_at: str,
    image_url: str,
    layout: str = "normal",
    type_line: str = "Instant",
) -> dict:
    return {
        "id": card_id,
        "oracle_id": oracle_id,
        "name": name,
        "set": set_code,
        "set_name": set_name,
        "collector_number": collector_number,
        "released_at": released_at,
        "layout": layout,
        "type_line": type_line,
        "image_uris": {
            "png": image_url,
            "normal": image_url.replace(".png", "-normal.png"),
            "small": image_url.replace(".png", "-small.png"),
        },
    }


def test_default_core_paths_use_app_data_root():
    assert core_data_root() == data_root() / "mtg_core"
    assert Path(default_db_path()) == core_data_root() / "card_data.sqlite3"
    service = CardService()
    assert Path(service.image_root) == core_data_root() / "images"


def test_fetch_missing_card_persists_and_returns_cached_local():
    runtime_dir = _workspace_runtime_dir("fetch_missing_card")
    calls: list[str] = []

    def fake_fetch_json(url: str) -> dict:
        calls.append(url)
        return _sample_print(
            card_id="card-opt-1",
            oracle_id="oracle-opt",
            name="Opt",
            set_code="eld",
            set_name="Throne of Eldraine",
            collector_number="59",
            released_at="2019-10-04",
            image_url="https://img.test/opt.png",
        )

    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=fake_fetch_json,
    )

    remote = service.fetch_missing_card(exact_name="Opt")
    cached = service.get_card(exact_name="Opt")
    results = service.search_cards("Opt", {"allow_remote": False})

    assert remote["id"] == "card-opt-1"
    assert cached["id"] == "card-opt-1"
    assert [result.card_id for result in results] == ["card-opt-1"]
    assert len(calls) == 1


def test_search_cards_remote_fill_sets_canonical_print_and_sync_bulk_data():
    runtime_dir = _workspace_runtime_dir("search_cards")
    calls: list[str] = []

    def fake_fetch_json(url: str) -> dict:
        calls.append(url)
        return {
            "object": "list",
            "data": [
                _sample_print(
                    card_id="bolt-alpha",
                    oracle_id="oracle-bolt",
                    name="Lightning Bolt",
                    set_code="lea",
                    set_name="Limited Edition Alpha",
                    collector_number="161",
                    released_at="1993-08-05",
                    image_url="https://img.test/bolt-alpha.png",
                ),
                _sample_print(
                    card_id="bolt-m11",
                    oracle_id="oracle-bolt",
                    name="Lightning Bolt",
                    set_code="m11",
                    set_name="Magic 2011",
                    collector_number="146",
                    released_at="2010-07-16",
                    image_url="https://img.test/bolt-m11.png",
                ),
            ],
            "has_more": False,
        }

    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=fake_fetch_json,
        fetch_bulk_fn=lambda: [
            _sample_print(
                card_id="opt-eld",
                oracle_id="oracle-opt",
                name="Opt",
                set_code="eld",
                set_name="Throne of Eldraine",
                collector_number="59",
                released_at="2019-10-04",
                image_url="https://img.test/opt.png",
            )
        ],
    )

    results = service.search_cards("Lightning Bolt", {"set_filter": "alpha"})
    canonical = service.get_canonical_print("oracle-bolt")
    bulk_result = service.sync_bulk_data()
    imported = service.get_card(exact_name="Opt")

    assert [result.card_id for result in results] == ["bolt-alpha"]
    assert canonical["id"] == "bolt-alpha"
    assert bulk_result == {"synced": 1, "status": "ok"}
    assert imported["id"] == "opt-eld"
    assert 'q=%21%22Lightning+Bolt%22' in calls[0]


def test_ensure_image_records_manifest_and_reuses_cached_file():
    runtime_dir = _workspace_runtime_dir("ensure_image")
    byte_calls: list[str] = []

    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda url: _sample_print(
            card_id="card-1",
            oracle_id="oracle-1",
            name="Plains",
            set_code="lea",
            set_name="Limited Edition Alpha",
            collector_number="232",
            released_at="1993-08-05",
            image_url="https://img.test/plains.png",
        ),
        fetch_bytes_fn=lambda url: byte_calls.append(url) or b"png-bytes",
    )

    service.fetch_missing_card(card_id="card-1")
    first_path = service.ensure_image("card-1")
    second_path = service.ensure_image("card-1")

    assert first_path == second_path
    assert first_path is not None
    assert Path(first_path).exists()
    assert service.get_image_path("card-1") == first_path
    assert byte_calls == ["https://img.test/plains.png"]


def test_materialize_image_asset_uses_asset_id_when_preferred_name_matches():
    runtime_dir = _workspace_runtime_dir("materialize_same_name")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
    )
    old_asset_id = service.store_image_bytes(b"old-art", extension="png", source="test")
    new_asset_id = service.store_image_bytes(b"new-art", extension="png", source="test")
    output_root = runtime_dir / "materialized"

    old_path = service.materialize_image_asset(
        old_asset_id,
        preferred_name="scryfall_sos_274_island.png",
        output_root=str(output_root),
    )
    new_path = service.materialize_image_asset(
        new_asset_id,
        preferred_name="scryfall_sos_274_island.png",
        output_root=str(output_root),
    )
    repeated_new_path = service.materialize_image_asset(
        new_asset_id,
        preferred_name="scryfall_sos_274_island.png",
        output_root=str(output_root),
    )

    assert old_path is not None
    assert new_path is not None
    assert old_path != new_path
    assert old_asset_id in Path(old_path).name
    assert new_asset_id in Path(new_path).name
    assert repeated_new_path == new_path
    assert Path(old_path).read_bytes() == b"old-art"
    assert Path(new_path).read_bytes() == b"new-art"


def test_materialize_image_asset_rewrites_corrupt_existing_cache_file():
    runtime_dir = _workspace_runtime_dir("materialize_rewrite_corrupt")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
    )
    asset_id = service.store_image_bytes(b"real-art", extension="png", source="test")

    path = service.materialize_image_asset(
        asset_id,
        preferred_name="same-card.png",
        output_root=str(runtime_dir / "materialized"),
    )
    assert path is not None
    Path(path).write_bytes(b"stale-or-corrupt")

    rematerialized_path = service.materialize_image_asset(
        asset_id,
        preferred_name="same-card.png",
        output_root=str(runtime_dir / "materialized"),
    )

    assert rematerialized_path == path
    assert Path(path).read_bytes() == b"real-art"


def test_search_cards_returns_local_results_when_remote_lookup_is_unavailable():
    runtime_dir = _workspace_runtime_dir("search_cards_offline_local")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
    )
    service.database.upsert_card_payload(
        _sample_print(
            card_id="bolt-local",
            oracle_id="oracle-bolt",
            name="Lightning Bolt",
            set_code="lea",
            set_name="Limited Edition Alpha",
            collector_number="161",
            released_at="1993-08-05",
            image_url="https://img.test/bolt-local.png",
        )
    )

    results = service.search_cards("Lightning Bolt", {"allow_remote": True})

    assert [result.card_id for result in results] == ["bolt-local"]


def test_search_cards_raises_friendly_offline_error_when_no_local_results_exist():
    runtime_dir = _workspace_runtime_dir("search_cards_offline_empty")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
    )

    try:
        service.search_cards("Mystic Tutor", {"allow_remote": True})
    except RemoteLookupUnavailable as exc:
        assert "offline" in str(exc)
    else:
        raise AssertionError("Expected offline search to raise when no local results exist.")


def test_ensure_image_raises_offline_error_only_when_remote_download_is_required():
    runtime_dir = _workspace_runtime_dir("ensure_image_offline")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
        fetch_bytes_fn=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
    )

    try:
        service.ensure_image("missing-card")
    except RemoteLookupUnavailable as exc:
        assert "offline" in str(exc)
    else:
        raise AssertionError("Expected ensure_image to raise when the image is missing locally.")


def test_search_cards_ranks_prefix_matches_before_substring_matches():
    runtime_dir = _workspace_runtime_dir("search_rank_prefix")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
    )
    for payload in [
        _sample_print(
            card_id="tuna-can",
            oracle_id="oracle-tuna",
            name='"2 Seconds After Opening the Tuna Can"',
            set_code="sos",
            set_name="Secret Lair",
            collector_number="7",
            released_at="2025-01-01",
            image_url="https://img.test/tuna.png",
        ),
        _sample_print(
            card_id="aang",
            oracle_id="oracle-aang",
            name="Aang, Air Nomad",
            set_code="tle",
            set_name="Avatar",
            collector_number="210",
            released_at="2025-01-02",
            image_url="https://img.test/aang.png",
        ),
        _sample_print(
            card_id="ach",
            oracle_id="oracle-ach",
            name='"Ach! Hans, Run!"',
            set_code="unh",
            set_name="Unhinged",
            collector_number="116",
            released_at="2004-11-19",
            image_url="https://img.test/ach.png",
        ),
    ]:
        service.database.upsert_card_payload(payload)

    results = service.search_cards("a", {"allow_remote": False, "limit": 10})

    assert [result.card_id for result in results] == ["aang", "ach", "tuna-can"]


def test_search_cards_returns_aang_matches_for_broad_name_fragment():
    runtime_dir = _workspace_runtime_dir("search_rank_aang")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
    )
    service.database.upsert_card_payload(
        _sample_print(
            card_id="aang",
            oracle_id="oracle-aang",
            name="Aang, Air Nomad",
            set_code="tle",
            set_name="Avatar",
            collector_number="210",
            released_at="2025-01-02",
            image_url="https://img.test/aang.png",
        )
    )

    results = service.search_cards("aang", {"allow_remote": False, "limit": 10})

    assert [result.name for result in results] == ["Aang, Air Nomad"]


def test_scryfall_search_falls_back_from_newer_no_match_error_wording():
    calls: list[str] = []

    def fake_fetch_json(url: str) -> dict:
        calls.append(url)
        if 'q=%21%22pla%22' in url:
            raise ValueError(
                "Your query didn't match any cards. Adjust your search terms or refer to the syntax guide at https://scryfall.com/docs/reference"
            )
        return {
            "object": "list",
            "data": [
                _sample_print(
                    card_id="plains",
                    oracle_id="oracle-plains",
                    name="Plains",
                    set_code="lea",
                    set_name="Limited Edition Alpha",
                    collector_number="286",
                    released_at="1993-08-05",
                    image_url="https://img.test/plains.png",
                )
            ],
            "has_more": False,
        }

    results = search_prints_payloads("pla", fetch_json_fn=fake_fetch_json)

    assert [result["name"] for result in results] == ["Plains"]
    assert len(calls) == 2


def test_token_keyword_filters_local_search_to_token_rows():
    runtime_dir = _workspace_runtime_dir("search_token_keyword")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
    )
    service.database.upsert_card_payload(
        _sample_print(
            card_id="ooze-card",
            oracle_id="oracle-ooze-card",
            name="Ooze Garden",
            set_code="ala",
            set_name="Shards of Alara",
            collector_number="142",
            released_at="2008-10-03",
            image_url="https://img.test/ooze-garden.png",
            type_line="Enchantment",
        )
    )
    service.database.upsert_card_payload(
        _sample_print(
            card_id="ooze-token",
            oracle_id="oracle-ooze-token",
            name="Ooze",
            set_code="tmid",
            set_name="Innistrad: Midnight Hunt Tokens",
            collector_number="10",
            released_at="2021-09-24",
            image_url="https://img.test/ooze-token.png",
            layout="token",
            type_line="Token Creature — Ooze",
        )
    )

    regular = service.search_cards("ooze", {"allow_remote": False, "limit": 10})
    tokens = service.search_cards("ooze token", {"allow_remote": False, "limit": 10})

    assert [result.card_id for result in regular] == ["ooze-card"]
    assert [result.card_id for result in tokens] == ["ooze-token"]


def test_token_remote_search_uses_extras_and_persists_token_payload():
    runtime_dir = _workspace_runtime_dir("search_token_remote")
    calls: list[str] = []

    def fake_fetch_json(url: str) -> dict:
        calls.append(url)
        assert "include=extras" in url
        assert "t%3Atoken" in url
        return {
            "object": "list",
            "data": [
                _sample_print(
                    card_id="ooze-token",
                    oracle_id="oracle-ooze-token",
                    name="Ooze",
                    set_code="tmid",
                    set_name="Innistrad: Midnight Hunt Tokens",
                    collector_number="10",
                    released_at="2021-09-24",
                    image_url="https://img.test/ooze-token.png",
                    layout="token",
                    type_line="Token Creature — Ooze",
                )
            ],
            "has_more": False,
        }

    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=fake_fetch_json,
    )

    results = service.search_cards("ooze token", {"allow_remote": True, "limit": 10})
    cached = service.search_cards("ooze token", {"allow_remote": False, "limit": 10})

    assert [result.card_id for result in results] == ["ooze-token"]
    assert [result.card_id for result in cached] == ["ooze-token"]
    assert calls == [build_print_search_url("t:token ooze", include_extras=True)]


def test_token_mode_offline_search_returns_local_or_raises_when_missing():
    runtime_dir = _workspace_runtime_dir("search_token_offline")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: (_ for _ in ()).throw(RemoteLookupUnavailable("offline")),
    )
    service.database.upsert_card_payload(
        _sample_print(
            card_id="ooze-token",
            oracle_id="oracle-ooze-token",
            name="Ooze",
            set_code="tmid",
            set_name="Innistrad: Midnight Hunt Tokens",
            collector_number="10",
            released_at="2021-09-24",
            image_url="https://img.test/ooze-token.png",
            layout="token",
            type_line="Token Creature — Ooze",
        )
    )

    local = service.search_cards("ooze token", {"allow_remote": True, "limit": 10})
    try:
        service.search_cards("goblin token", {"allow_remote": True, "limit": 10})
    except RemoteLookupUnavailable as exc:
        assert "offline" in str(exc)
    else:
        raise AssertionError("Expected missing token search to raise when offline.")

    assert [result.card_id for result in local] == ["ooze-token"]


def test_online_mode_search_uses_only_recent_online_cache_rows():
    runtime_dir = _workspace_runtime_dir("online_cache_scope")
    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=lambda _url: (_ for _ in ()).throw(AssertionError("remote search should not run")),
    )
    service.database.upsert_card_payload(
        _sample_print(
            card_id="opt-durable",
            oracle_id="oracle-opt-durable",
            name="Opt",
            set_code="eld",
            set_name="Throne of Eldraine",
            collector_number="59",
            released_at="2019-10-04",
            image_url="https://img.test/opt-durable.png",
        )
    )
    service.database.upsert_card_payload(
        _sample_print(
            card_id="opt-online",
            oracle_id="oracle-opt-online",
            name="Opt",
            set_code="dom",
            set_name="Dominaria",
            collector_number="60",
            released_at="2018-04-27",
            image_url="https://img.test/opt-online.png",
        ),
        cache_scope="online_search",
        cache_expires_at=9999999999,
    )
    service.database.upsert_card_payload(
        _sample_print(
            card_id="opt-expired",
            oracle_id="oracle-opt-expired",
            name="Opt",
            set_code="inv",
            set_name="Invasion",
            collector_number="64",
            released_at="2000-10-02",
            image_url="https://img.test/opt-expired.png",
        ),
        cache_scope="online_search",
        cache_expires_at=1,
    )

    online = service.search_cards("Opt", {"online_mode": True, "allow_remote": False})
    offline = service.search_cards("Opt", {"online_mode": False, "allow_remote": False})

    assert [result.card_id for result in online] == ["opt-online"]
    assert [result.card_id for result in offline] == ["opt-durable"]


def test_online_mode_remote_results_are_cached_with_ttl():
    runtime_dir = _workspace_runtime_dir("online_cache_remote")
    calls: list[str] = []

    def fake_fetch_json(url: str) -> dict:
        calls.append(url)
        return {
            "object": "list",
            "data": [
                _sample_print(
                    card_id="opt-online",
                    oracle_id="oracle-opt-online",
                    name="Opt",
                    set_code="dom",
                    set_name="Dominaria",
                    collector_number="60",
                    released_at="2018-04-27",
                    image_url="https://img.test/opt-online.png",
                )
            ],
            "has_more": False,
        }

    service = CardService(
        db_path=str(runtime_dir / "card_data.sqlite3"),
        image_root=str(runtime_dir / "images"),
        fetch_json_fn=fake_fetch_json,
    )

    first = service.search_cards("Opt", {"online_mode": True, "allow_remote": True, "cache_ttl_seconds": 60})
    second = service.search_cards("Opt", {"online_mode": True, "allow_remote": True, "cache_ttl_seconds": 60})
    offline = service.search_cards("Opt", {"online_mode": False, "allow_remote": False})

    assert [result.card_id for result in first] == ["opt-online"]
    assert [result.card_id for result in second] == ["opt-online"]
    assert offline == []
    assert calls == [build_print_search_url('!"Opt"', include_extras=False)]
