"""Offline cohort isolation and resumable expansion coverage for CI."""

import gzip
import hashlib
import json

import pytest

from mtg_core.edhrec import EdhrecSource, normalize, save_page
from mtg_core.edhrec_cohorts import CohortDownloader, cohort_options, cohort_path, collect, variants


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
