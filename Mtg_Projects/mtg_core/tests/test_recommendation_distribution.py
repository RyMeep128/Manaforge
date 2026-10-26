from contextlib import closing
from dataclasses import replace
import json
import importlib.util
from pathlib import Path
import shutil
import sqlite3
import uuid
import zipfile

import pytest

from mtg_core.datasets import InstallationState, parse_manifest
from mtg_core.downloads import DownloadManager
from mtg_core.edhrec import EdhrecSource, save_page
from mtg_core.recommendation_distribution import (
    RecommendationDistribution,
    validate_bundle,
)
from mtg_core.recommendation_packaging import build_distribution, export_statistics
from mtg_core.recommendations import RecommendationStore
from mtg_core.recommendation_sources import default_sources
from mtg_core.released_recommendations import ReleasedRecommendationSource


IDS = [str(uuid.UUID(int=i)) for i in range(1, 7)]


def collected(root, source="archidekt"):
    root.mkdir(parents=True, exist_ok=True)
    store = RecommendationStore(root / (source + ".sqlite3"))
    a, b, c, d, e, _ = IDS
    for i, members in enumerate(
        ({a: 1, c: 0, d: 0}, {a: 1, b: 1, c: 0}, {a: 1, b: 1, e: 0}, {b: 1, d: 0})
    ):
        store.ingest_members(
            "private-deck-" + str(i),
            "digest-" + str(i),
            "https://private.example/user/" + str(i),
            members,
        )
    return store


def test_aggregate_export_preserves_scores_pairs_reverse_lookup_and_associations(
    tmp_path,
):
    store = collected(tmp_path / "private")
    output = tmp_path / "aggregates.sqlite3"
    export_statistics(store.path, output, "archidekt", report=lambda *a, **k: None)
    released = ReleasedRecommendationSource(output, "archidekt")
    for commanders in ([], [IDS[0]], [IDS[1]], [IDS[0], IDS[1]], [IDS[-1]]):
        old, new = store.snapshot(commanders), released.snapshot(commanders)
        assert new["results"] == old["results"]
        assert (
            new["decks"] == old["decks"]
            and new["relevant_decks"] == old["relevant_decks"]
        )
    for candidate in IDS:
        assert released.commanders_using(candidate) == store.commanders_using(candidate)
    for seeds in ([IDS[0]], IDS[:3], [IDS[-1]], IDS):
        assert released.associations(seeds, IDS) == store.associations(seeds, IDS)
    assert (
        b"private-deck" not in output.read_bytes()
        and b"private.example" not in output.read_bytes()
    )
    with closing(sqlite3.connect(output)) as db:
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name IN ('decks','members')"
        ).fetchall()


def test_build_reuses_unchanged_inputs_and_never_packages_unapproved_sources(
    tmp_path, monkeypatch
):
    root, output = tmp_path / "private", tmp_path / "output"
    collected(root)
    (root / "local.sqlite3").write_bytes(b"personal private data")
    manifest = build_distribution(
        root, output, "2026.10.26-alpha.1", sources=["archidekt"]
    )
    entry = parse_manifest(manifest)[0]
    archive = output / Path(entry.url).name
    with zipfile.ZipFile(archive) as package:
        assert set(package.namelist()) == {"bundle.json", "aggregates.sqlite3"}

    def unexpected(*args, **kwargs):
        raise AssertionError("Unchanged source was regenerated")

    monkeypatch.setattr(
        "mtg_core.recommendation_packaging.export_statistics", unexpected
    )
    assert (
        build_distribution(root, output, "2026.10.26-alpha.1", sources=["archidekt"])[
            "datasets"
        ]
        == manifest["datasets"]
    )
    with pytest.raises(ValueError, match="approval"):
        build_distribution(root, output, "2026.10.26-alpha.1", sources=["playgroup"])


def test_install_activates_existing_adapter_without_running_collectors(tmp_path):
    root, output = tmp_path / "private", tmp_path / "output"
    collected(root)
    manifest = build_distribution(
        root, output, "2026.10.26-alpha.1", sources=["archidekt"]
    )
    state = InstallationState(tmp_path / "client" / "state.sqlite3")
    state.set("recommendations_root", str(tmp_path / "client" / "data"))

    class LocalDownload:
        def download(self, url, destination, **kwargs):
            shutil.copyfile(output / Path(url).name, destination)

    distribution = RecommendationDistribution(state, LocalDownload())
    entries, unavailable = distribution.available(manifest)
    assert len(entries) == 1 and not unavailable
    installed = distribution.install(entries[0])
    validate_bundle(installed, "archidekt")
    assert distribution.available(manifest) == ([], [])
    personal = RecommendationStore(tmp_path / "user" / "local.sqlite3")
    sources = default_sources(personal, distribution_state=state)
    source = next(source for source in sources if source.source_id == "archidekt")
    assert isinstance(source, ReleasedRecommendationSource)
    assert source.snapshot([IDS[0]])["relevant_decks"] == 3
    future = replace(entries[0], schema_version=2)
    with pytest.raises(ValueError, match="schema"):
        distribution.install(future)
    assert state.installed(entries[0].dataset_id)["path"] == str(installed)


def test_edhrec_publication_preserves_normalized_scores_and_strips_unknown_fields(
    tmp_path,
):
    root, output = tmp_path / "private", tmp_path / "output"
    root.mkdir()
    row = dict(
        oracle_id=IDS[2],
        inclusion=0.5,
        score=0.5,
        sample=20,
        num_decks=10,
        baseline=0.0,
        synergy=0.0,
        commander=IDS[0],
        commanders=[IDS[0]],
        categories=["Draw"],
        edhrec_synergy=0.2,
        statistics_source="edhrec",
        private_owner="secret",
    )
    page = dict(
        commander=IDS[0],
        commanders=[IDS[0]],
        slug="fixture",
        sample=20,
        results=[row],
        unresolved=[],
        raw_decks=[dict(owner="secret")],
    )
    save_page(root / "edhrec.sqlite3", page, 1_700_000_000)
    manifest = build_distribution(
        root, output, "2026.10.26-alpha.1", sources=["edhrec"]
    )
    archive = output / Path(manifest["datasets"][0]["url"]).name
    target = tmp_path / "expanded"
    with zipfile.ZipFile(archive) as package:
        package.extractall(target)
    validate_bundle(target, "edhrec")
    with closing(sqlite3.connect(target / "edhrec.sqlite3")) as db:
        data = json.loads(db.execute("SELECT payload FROM pages").fetchone()[0])
    assert "raw_decks" not in data and "private_owner" not in data["results"][0]
    original = EdhrecSource(root / "edhrec.sqlite3").snapshot([IDS[0]])
    installed = EdhrecSource(target / "edhrec.sqlite3").snapshot([IDS[0]])
    original["results"][0].pop("private_owner")
    assert installed["results"] == original["results"]
    assert installed["relevant_decks"] == original["relevant_decks"]


def test_failed_manifest_check_preserves_working_manifest_and_check_timestamp(
    tmp_path, monkeypatch
):
    import io
    from mtg_core import downloads

    monkeypatch.setattr(downloads, "wait_for_request", lambda *a, **k: None)

    class Response(io.BytesIO):
        status = 200
        headers = {}

        def geturl(self):
            return "https://fixtures.example/manifest.json"

    state = InstallationState(tmp_path / "state.sqlite3")
    path = tmp_path / "recommendation-manifest.json"
    path.write_bytes(b"working")
    state.set("last_successful_update_check", 123)
    distribution = RecommendationDistribution(
        state,
        DownloadManager(opener=lambda *a, **k: Response(b'{"manifest_version":99}')),
    )
    with pytest.raises(ValueError, match="manifest"):
        distribution.check("https://fixtures.example/manifest.json")
    assert path.read_bytes() == b"working"
    assert state.get("last_successful_update_check") == 123


def publisher_module():
    path = Path(__file__).resolve().parents[3] / "tools" / "recommendation_data.py"
    spec = importlib.util.spec_from_file_location("recommendation_data_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reopening_install_registry_does_not_invalidate_recommendation_cache(tmp_path):
    state = InstallationState(tmp_path / "state.sqlite3")
    state.set("setup_complete", True)
    before = state.path.read_bytes()
    reopened = InstallationState(state.path)
    assert reopened.get("setup_complete") is True
    assert reopened.path.read_bytes() == before


def test_existing_cohort_selectors_can_read_the_installed_dataset(
    tmp_path, monkeypatch
):
    from mtg_core.edhrec_cohorts import cohort_options

    installed = tmp_path / "installed-cohorts.sqlite3"
    with closing(sqlite3.connect(installed)) as db, db:
        db.execute("CREATE TABLE cohorts(kind TEXT,value TEXT,label TEXT)")
        db.execute("INSERT INTO cohorts VALUES (?,?,?)", ("theme", "tokens", "Tokens"))
    monkeypatch.setattr(
        "mtg_core.recommendation_distribution.released_file", lambda *args: installed
    )
    assert cohort_options(tmp_path / "recommendations" / "edhrec-cohorts.sqlite3") == [
        ("theme", "tokens", "Tokens")
    ]


def test_staging_uses_draft_prerelease_and_manifest_asset_allowlist(tmp_path):
    root, output = tmp_path / "private", tmp_path / "output"
    collected(root)
    build_distribution(root, output, "2026.10.26-alpha.1", sources=["archidekt"])
    (output / "private-response.json").write_text("never upload")
    tool = publisher_module()

    class GitHub:
        repository = "RyMeep128/Manaforge"

        def __init__(self):
            self.calls = []
            self.uploads = []

        def release(self, tag):
            return None

        def request(self, path, **kwargs):
            self.calls.append((path, kwargs))
            return {"html_url": "https://github.com/fixture/draft", "assets": []}

        def upload(self, release, path):
            self.uploads.append(path.name)

    github = GitHub()
    tool.stage(github, output, "a" * 40, "infrastructure-readiness", True)
    assert github.calls[0][1]["data"]["draft"] is True
    assert github.calls[0][1]["data"]["prerelease"] is True
    assert set(github.uploads) == {"manifest.json", next(output.glob("*.zip")).name}
    assert github.calls[-1][0].endswith("/dispatches")


def test_publication_rejects_a_different_ci_commit_before_any_release_changes(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"version": "2026.10.26-alpha.1"}))
    tool = publisher_module()

    class GitHub:
        def release(self, tag):
            return {"target_commitish": "b" * 40}

        def request(self, *args, **kwargs):
            raise AssertionError("Unverified release changed")

    with pytest.raises(ValueError, match="CI-tested"):
        tool.promote(GitHub(), tmp_path, "a" * 40)
