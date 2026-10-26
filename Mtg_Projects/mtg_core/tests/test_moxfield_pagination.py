import hashlib
import json
from types import SimpleNamespace

import pytest

from mtg_core.moxfield_ingest import Collector


def collector(tmp_path, fetch):
    instance = Collector.__new__(Collector)
    instance.path = tmp_path / "state.json"
    instance.max_decks = 20000
    instance.max_pages = 200
    instance.downloader = SimpleNamespace(wait=lambda _: None)
    instance.fetch = fetch
    signature = hashlib.sha256(json.dumps(["old"]).encode()).hexdigest()
    instance.state = dict(
        version=1, imported=0, queue=[], seen=["old", "new"],
        listings={"/v2/decks/search": dict(page=122, done=False, signatures=[signature])},
        last_error="Previous repeated page",
    )
    return instance


def page(deck, total=122):
    return dict(data=[dict(publicId=deck)], totalPages=total)


def test_cached_repeat_is_refetched_and_final_page_finishes(tmp_path):
    calls = []

    def fetch(path, params, *, refresh=False):
        calls.append((params["pageNumber"], refresh))
        return page("new" if refresh else "old")

    instance = collector(tmp_path, fetch)
    result = instance.run(search=True)
    assert calls == [(122, False), (122, True)]
    assert result["status"] == "complete"
    assert result["last_error"] is None
    assert result["listings"]["/v2/decks/search"]["done"]


def test_persistent_repeat_skips_page_with_visible_coverage_gap(tmp_path):
    calls = []

    def fetch(path, params, *, refresh=False):
        calls.append((params["pageNumber"], refresh))
        return page("old" if params["pageNumber"] == 122 else "new", total=123)

    instance = collector(tmp_path, fetch)
    result = instance.run(search=True)
    assert calls == [(122, False), (122, True), (122, True), (123, False)]
    assert result["status"] == "complete"
    assert result["listings"]["/v2/decks/search"]["skipped_pages"] == [122]
    assert "Skipped repeated listing page 122" in result["last_warning"]


def test_repeated_pages_stop_after_bounded_retries(tmp_path):
    calls = []

    def fetch(path, params, *, refresh=False):
        calls.append(params["pageNumber"])
        return page("old", total=157)

    instance = collector(tmp_path, fetch)
    with pytest.raises(ValueError, match="Three consecutive"):
        instance.run(search=True)
    assert calls == [122] * 3 + [123] * 3 + [124] * 3
    assert instance.state["status"] == "error"


def test_author_checkpoint_uses_filtered_search(tmp_path):
    calls = []

    def fetch(path, params, **kwargs):
        calls.append((path, params))
        return dict(data=[], totalPages=0)

    instance = collector(tmp_path, fetch)
    instance.state["listings"] = {"/v2/users/Some%20User/decks": dict(page=1, done=False)}
    result = instance.run()
    assert result["status"] == "complete"
    assert calls[0][0] == "/v2/decks/search"
    assert calls[0][1]["authorUserNames"] == "Some User"
    assert calls[0][1]["fmt"] == "commander"
