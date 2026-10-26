"""Offline CI coverage for source normalization and recommendation integration."""

import json
import uuid

import pytest

from mtg_core.public_deck_datasets import DATASET_LABELS
from mtg_core.public_deck_ingest import Collector, METAGAME, PLAYGROUP, PRECONS, normalize_rows, text_rows
from mtg_core.recommendation_cache import save_source_settings, set_mode, source_settings
from mtg_core.recommendation_sources import default_sources, recommend
from mtg_core.recommendations import RecommendationStore


COMMANDER, FOREST = (str(uuid.UUID(int=value)) for value in (1, 2))
NAMES = {"leader": COMMANDER, "forest": FOREST}


@pytest.mark.parametrize("source", DATASET_LABELS)
def test_collected_samples_feed_recommendations_and_resume(tmp_path, monkeypatch, source):
    monkeypatch.setattr("mtg_core.public_deck_ingest.catalog_index", lambda _: (NAMES, {}))
    collector = Collector(source, tmp_path / f"{source}-run", tmp_path / "catalog.sqlite3", user_agent="CI")
    responses, inputs = {}, []
    if source == "preconstructed":
        responses[PRECONS] = json.dumps([
            dict(format="standard", set_code="fixture", name="Unlisted product", set_name="Fixture set",
                 release_date="2020-01-01", cards=[]),
            dict(format="commander", set_code="fixture", set_name="Fixture set", name="Precon", release_date="2020-01-01",
                 cards=[dict(name="Forest", count=99)], commander=[dict(name="Leader", count=1)],
                 displayCommander=[dict(name="Oversized Leader", count=1)]),
        ])
    elif source == "metagame":
        responses[METAGAME + "manifest.json"] = json.dumps(dict(formats=[
            dict(id="modern", decks=[dict(file="should-not-fetch.txt")]),
            dict(id="commander", decks=[dict(file="01-leader.txt")]),
        ]))
        responses[METAGAME + "decks/commander/01-leader.txt"] = "99 Forest\n\n1 Leader\n"
    elif source == "playgroup":
        # Two tracking records share a hosted deck and must count only once.
        responses[PLAYGROUP + "users/1/decks"] = json.dumps([
            dict(id=value, archived=False, decklist_url="https://moxfield.com/decks/public")
            for value in (1, 2)
        ])
        responses["https://api2.moxfield.com/v3/decks/all/public"] = json.dumps(dict(
            format="commander", visibility="public", boards=dict(
                mainboard=dict(cards=dict(a=dict(quantity=99, card=dict(name="Forest")))),
                commanders=dict(cards=dict(b=dict(quantity=1, card=dict(name="Leader")))),
            ),
        ))
        inputs = [dict(kind="user", value="1")]
    else:
        export = tmp_path / "export.txt"
        export.write_text("1 Leader\n99 Forest\n\n1 Unknown Sideboard Card\n", encoding="utf-8")
        inputs = [dict(kind="file", value=str(export), commanders=["Leader"], url=export.as_uri())]
    monkeypatch.setattr(collector, "fetch", responses.__getitem__)
    assert collector.run(inputs)["imported"] == 1
    assert collector.run([])["imported"] == 1
    local = RecommendationStore(tmp_path / "local.sqlite3")
    result = recommend(default_sources(local), [COMMANDER], exclude=[COMMANDER])
    assert result["public_sources"] == [source]
    row = result["results"][0]
    assert row["oracle_id"] == FOREST
    assert row["source_evidence"][source]["sample"] == 1
    config = source_settings(tmp_path)
    config[source]["enabled"] = False
    save_source_settings(tmp_path, config)
    assert not recommend(default_sources(local), [COMMANDER])["results"]


def test_incomplete_or_unresolved_exports_do_not_publish_partial_samples():
    with pytest.raises(ValueError, match="Unresolved"):
        normalize_rows([("Leader", 1, True), ("Unknown", 99, False)], NAMES)
    with pytest.raises(ValueError, match="100"):
        normalize_rows([("Leader", 1, True), ("Forest", 98, False)], NAMES)
    with pytest.raises(ValueError, match="one copy"):
        normalize_rows([("Leader", 2, True), ("Forest", 98, False)], NAMES)
    with pytest.raises(ValueError, match="Unrecognized"):
        text_rows("Not a counted card line")


def test_sideboard_is_only_a_commander_section_for_the_metagame_dataset():
    text = "99 Forest\n\n1 Leader\n"
    assert not any(row[2] for row in text_rows(text))
    assert normalize_rows(text_rows(text, sideboard_commanders=True), NAMES) == {FOREST: 0, COMMANDER: 1}
    with pytest.raises(ValueError, match="already occur"):
        text_rows(text, commanders=["Leader"])


def test_disabled_legacy_settings_do_not_enable_new_sources(tmp_path):
    (tmp_path / "source-settings.json").write_text(json.dumps(dict(
        version=2, archidekt=dict(enabled=False, cache="live"), edhrec=dict(enabled=False),
        moxfield=dict(enabled=False),
    )), encoding="utf-8")
    assert all(not source_settings(tmp_path)[key]["enabled"] for key in DATASET_LABELS)
    save_source_settings(tmp_path, source_settings(tmp_path))
    set_mode(tmp_path, "disabled")
    assert all(not source_settings(tmp_path)[key]["enabled"] for key in DATASET_LABELS)


def test_playgroup_metadata_without_a_card_list_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("mtg_core.public_deck_ingest.catalog_index", lambda _: (NAMES, {}))
    collector = Collector("playgroup", tmp_path / "playgroup-run", tmp_path / "catalog", user_agent="CI")
    monkeypatch.setattr(collector, "fetch", lambda _: json.dumps(dict(id=1, name="Metadata only")))
    state = collector.run([dict(kind="deck", value="1")])
    assert state["imported"] == 0
    assert "no supported public" in state["rejected"]["playgroup:1"]
