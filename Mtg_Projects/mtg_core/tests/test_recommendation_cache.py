from copy import deepcopy
import gzip
import hashlib
import json
import uuid

import pytest

from mtg_core.recommendations import RecommendationStore
from mtg_core.recommendation_cache import (
    AggregateSource,
    download_cache,
    export_cache,
    read_cache,
    set_mode,
    validate,
)
from mtg_core.recommendation_sources import default_sources


def make_cache(tmp_path):
    commander, common, rare = [str(uuid.UUID(int=i)) for i in (1, 2, 3)]
    store = RecommendationStore(tmp_path / "archidekt.sqlite3")
    for i in range(15):
        members = {commander: 1, common: 0}
        if i == 0:
            members[rare] = 0
        store.ingest_members(
            f"private-deck-{i}", str(i), "https://private.example/deck", members
        )
    path = tmp_path / "archidekt.aggregate.json.gz"
    digest = export_cache(store, path)
    return path, digest, commander, common, rare


def test_personal_export_suppresses_small_cells_and_omits_deck_metadata(tmp_path):
    path, digest, commander, common, rare = make_cache(tmp_path)
    raw = gzip.decompress(path.read_bytes())
    assert b"private-deck" not in raw and b"https:" not in raw
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    data = read_cache(path)
    assert rare not in data["cohorts"][0]["counts"]
    assert data["popularity"][rare] == 1
    snapshot = AggregateSource(path).snapshot([commander], exclude=[commander])
    assert snapshot["relevant_decks"] == 15
    assert snapshot["results"][0]["oracle_id"] == common
    assert snapshot["results"][0]["inclusion"] == 1
    for mutation in (dict(schema_version=2), dict(raw_decks=[]), dict(decks=14)):
        invalid = deepcopy(data)
        invalid.update(mutation)
        with pytest.raises(ValueError):
            validate(invalid)
    local = RecommendationStore(tmp_path / "local.sqlite3")
    set_mode(tmp_path, "portable")
    assert isinstance(default_sources(local)[0], AggregateSource)
    set_mode(tmp_path, "disabled")
    assert default_sources(local)[0].snapshot()["results"] == []


def test_download_verifies_checksum_before_replacing_cache(tmp_path, monkeypatch):
    path, digest, *_ = make_cache(tmp_path)
    raw = path.read_bytes()

    class Response:
        url = "https://fixture.example/cache.gz"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return raw[:limit]

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response())
    destination = tmp_path / "downloaded.gz"
    destination.write_bytes(b"existing")
    with pytest.raises(ValueError, match="checksum"):
        download_cache(Response.url, "0" * 64, destination)
    assert destination.read_bytes() == b"existing"
    download_cache(Response.url, digest, destination)
    assert read_cache(destination) == json.loads(gzip.decompress(raw))
    with pytest.raises(ValueError, match="HTTPS"):
        download_cache("http://fixture.example/cache.gz", digest, destination)
