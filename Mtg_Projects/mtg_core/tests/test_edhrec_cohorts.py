"""Offline cohort isolation and resumable expansion coverage for CI."""

import gzip
import hashlib
import json
import sqlite3
import urllib.error

import pytest

from mtg_core.edhrec import EdhrecSource, normalize, save_page
from mtg_core.edhrec_cohorts import CohortDownloader, cohort_options, cohort_path, collect, variants
from mtg_core.edhrec_cohorts import combination_children, combination_path


def page(sample=100):
    return dict(
        tag_counts=[dict(count=10, slug="infect", value="Infect")],
        bracket_counts={"3": 20, "5": 0},
        budget_counts=dict(budget=10, middle=80, expensive=0),
        container=dict(json_dict=dict(
            card=dict(name="Commander", num_decks=sample),
            cardlists=[dict(header="Top Cards", cardviews=[dict(
                name="Card", num_decks=2, potential_decks=10,
            )])],
        )),
    )


def test_only_nonempty_advertised_single_filters_are_queued():
    assert list(variants(page())) == [
        ("theme", "infect", "Infect"),
        ("bracket", "upgraded", "Bracket 3: Upgraded"),
        ("budget", "budget", "Budget"),
    ]
    for path in ("../secret.json", "https://evil.test/data.json", "commanders/a/../../x.json", "commanders/a/b/c.json"):
        with pytest.raises(ValueError):
            cohort_path(path)


def test_expansion_resume_and_exact_reads_preserve_general_snapshot(tmp_path, monkeypatch):
    root = tmp_path / "edhrec-run"
    (root / "responses").mkdir(parents=True)
    names = {"commander": "commander-oracle", "card": "card-oracle"}
    monkeypatch.setattr("mtg_core.edhrec_cohorts.catalog_index", lambda _: (names, {}))
    original = page()
    cache = root / "responses" / (hashlib.sha256(b"commanders/commander.json").hexdigest() + ".json.gz")
    cache.write_bytes(gzip.compress(json.dumps(original).encode()))
    (root / "state.json").write_text(json.dumps(dict(completed=["commander"])), encoding="utf-8")
    general = tmp_path / "edhrec.sqlite3"
    save_page(general, normalize(original, lambda name: names.get(name.casefold()), "commander"), 1)
    calls = []

    def fetch(self, path):
        calls.append(path)
        result = page(5)
        result["container"]["breadcrumb"] = [{"/" + path.removesuffix(".json"): "Filtered"}]
        return result

    monkeypatch.setattr(CohortDownloader, "fetch", fetch)
    # Bound the first run, then resume from the SQLite queue.
    first = collect(root, tmp_path / "catalog", max_pages=1)
    assert first["status"] == "bounded" and first["pending"] == 2
    second = collect(root, tmp_path / "catalog")
    assert second["status"] == "complete" and second["imported"] == 3
    assert len(calls) == 3
    assert EdhrecSource(general).snapshot(["commander-oracle"])["decks"] == 100
    selected = EdhrecSource(general, cohort="theme:infect").snapshot(["commander-oracle"])
    assert selected["decks"] == 5
    assert selected["sources"][0]["source"].endswith("/commander/infect")
    assert selected["results"][0]["edhrec_cohort"]["value"] == "infect"
    assert len(cohort_options(tmp_path / "edhrec-cohorts.sqlite3")) == 3
    assert not EdhrecSource(general, cohort="theme:missing").snapshot(["commander-oracle"])["results"]
    assert not EdhrecSource(general, cohort="theme:infect").snapshot(["other", "commander-oracle"])["results"]
    (root / "STOP").touch()
    assert collect(root, tmp_path / "catalog")["status"] == "paused"


def test_invalid_cohort_setting_fails_explicitly(tmp_path):
    with pytest.raises(ValueError, match="cohort selection"):
        EdhrecSource(tmp_path / "edhrec.sqlite3", cohort="theme:../../secret")


def test_combination_traversal_uses_conditional_counts_and_canonical_order():
    children = list(combination_children(page(), "bracket", "upgraded", "Bracket 3"))
    assert [(key, route) for key, route, _ in children] == [
        ("bracket:upgraded|theme:infect", "upgraded/infect"),
        ("bracket:upgraded|budget:budget", "upgraded/budget"),
    ]
    assert list(combination_children(page(), "combined", "theme:infect|budget:budget", "Infect / Budget")) == []
    empty = dict(page(), tag_counts=[], budget_counts={"budget": 0})
    assert list(combination_children(empty, "bracket", "upgraded", "Bracket 3")) == []
    assert combination_path("commanders/commander/upgraded/infect/budget.json")
    for path in ("../data.json", "commanders/c/../../data.json", "commanders/c/a/b/c/d.json"):
        with pytest.raises(ValueError):
            combination_path(path)


def combination_snapshot(tmp_path, monkeypatch):
    root = tmp_path / "edhrec-run"
    (root / "responses").mkdir(parents=True)
    names = {"commander": "commander-oracle", "card": "card-oracle"}
    monkeypatch.setattr("mtg_core.edhrec_cohorts.catalog_index", lambda _: (names, {}))
    original = page()
    cached = root / "responses" / (hashlib.sha256(b"commanders/commander.json").hexdigest() + ".json.gz")
    cached.write_bytes(gzip.compress(json.dumps(original).encode()))
    (root / "state.json").write_text(json.dumps(dict(completed=["commander"])), encoding="utf-8")
    save_page(tmp_path / "edhrec.sqlite3", normalize(original, lambda name: names.get(name.casefold()), "commander"), 1)
    return root


def test_combination_collection_resumes_prioritizes_children_and_isolates_existing_data(tmp_path, monkeypatch):
    root = combination_snapshot(tmp_path, monkeypatch)
    calls = []

    def fetch(self, path):
        calls.append(path)
        result = page(5)
        result["container"]["breadcrumb"] = [{"/" + path.removesuffix(".json"): "Filtered"}]
        return result

    monkeypatch.setattr(CohortDownloader, "fetch", fetch)
    (root / "cohort-state.json").write_text('{"status":"running"}', encoding="utf-8")
    first = collect(root, tmp_path / "catalog", combinations=True, max_pages=2)
    assert first["status"] == "bounded" and first["combined_imported"] == 1
    assert calls[:2] == ["commanders/commander/infect.json", "commanders/commander/infect/budget.json"]
    second = collect(root, tmp_path / "catalog", combinations=True)
    assert second["status"] == "complete" and second["combined_imported"] == 4
    assert second["imported"] == len(calls) == len(set(calls)) == 6
    with sqlite3.connect(tmp_path / "edhrec-combinations.sqlite3") as db:
        rows = db.execute("SELECT kind,value,payload FROM cohorts").fetchall()
    assert len(rows) == 4 and all(kind == "combined" for kind, _, _ in rows)
    triple = next(json.loads(payload) for _, key, payload in rows if key == "bracket:upgraded|theme:infect|budget:budget")
    assert triple["cohort"]["filters"] == dict(bracket="upgraded", theme="infect", budget="budget")
    assert triple["sample"] == 5
    assert triple["source_path"].endswith("/upgraded/infect/budget")
    assert (root / "cohort-state.json").read_text(encoding="utf-8") == '{"status":"running"}'
    assert not (tmp_path / "edhrec-cohorts.sqlite3").exists()
    assert EdhrecSource(tmp_path / "edhrec.sqlite3").snapshot(["commander-oracle"])["decks"] == 100
    (root / "STOP").touch()
    assert collect(root, tmp_path / "catalog", combinations=True)["status"] == "paused"


@pytest.mark.parametrize("failure", ["missing", "redirected", "wrong-commander", "empty"])
def test_combination_collection_rejects_unavailable_or_mismatched_pages(tmp_path, monkeypatch, failure):
    root = combination_snapshot(tmp_path, monkeypatch)

    def fetch(self, path):
        if failure == "missing":
            raise urllib.error.HTTPError(path, 404, "Missing", {}, None)
        result = page(0 if failure == "empty" else 5)
        result["container"]["breadcrumb"] = [{"/" + path.removesuffix(".json"): "Filtered"}]
        if failure == "redirected":
            result["container"]["breadcrumb"] = [{"/commanders/commander": "General"}]
        if failure == "wrong-commander":
            result["container"]["json_dict"]["card"]["name"] = "Card"
        return result

    monkeypatch.setattr(CohortDownloader, "fetch", fetch)
    state = collect(root, tmp_path / "catalog", combinations=True)
    assert state["status"] == "complete"
    assert state["combined_imported"] == 0 and state["skipped"] == 2
