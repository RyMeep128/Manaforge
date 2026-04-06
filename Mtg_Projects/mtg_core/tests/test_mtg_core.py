from __future__ import annotations

import uuid
from pathlib import Path

from mtg_core.services import CardService


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
) -> dict:
    return {
        "id": card_id,
        "oracle_id": oracle_id,
        "name": name,
        "set": set_code,
        "set_name": set_name,
        "collector_number": collector_number,
        "released_at": released_at,
        "image_uris": {
            "png": image_url,
            "normal": image_url.replace(".png", "-normal.png"),
            "small": image_url.replace(".png", "-small.png"),
        },
    }


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
