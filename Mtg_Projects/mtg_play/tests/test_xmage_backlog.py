import importlib.util
import json
from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("backlog_tool", ROOT / "tools/build_xmage_backlog.py")
backlog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backlog)


def test_nonpaper_objects_do_not_become_paper_card_work():
    assert backlog.category(dict(type_line="Token Creature", games=["paper"])) == "token_dependency"
    assert backlog.category(dict(type_line="Sorcery", games=["arena"], digital=True)) == "digital_or_nonpaper"
    assert backlog.category(dict(type_line="Creature", games=["paper"], border_color="silver")) == "novelty"
    assert backlog.category(dict(type_line="Legendary Creature", games=["paper"], set_type="commander")) == "paper_rules"
    assert backlog.category(dict(layout="art_series", type_line="Card", games=["paper"])) == "non_game_or_unresolved"


def test_commented_or_unimplemented_upstream_registrations_are_not_evidence(tmp_path):
    def git(*args):
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    git("init")
    card = tmp_path / "Mage.Sets/src/mage/cards/a/Actual.java"
    card.parent.mkdir(parents=True)
    card.write_text("class Actual {}")
    source = tmp_path / "Mage.Sets/src/mage/sets/Set.java"
    source.parent.mkdir(parents=True)
    source.write_text('cards.add(new SetCardInfo("Actual", 1, Rarity.RARE, mage.cards.a.Actual.class));\n// cards.add(new SetCardInfo("Commented", 2, Rarity.RARE, mage.cards.a.Actual.class));\ncards.add(new SetCardInfo("Missing class", 3, Rarity.RARE, mage.cards.a.Missing.class));\n')
    git("add", ".")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture")
    revision, index = backlog.upstream_index(tmp_path, "HEAD")
    assert len(revision) == 40
    assert set(index) == {"actual"}


def test_behavioral_verification_requires_matching_source_and_engine(tmp_path):
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps(dict(fork_commit="expected", artifacts={"lib/mage-sets-1.jar": "hash"}, local_changes=[dict(tests="CardTest", reference="card.txt")])) )
    report = tmp_path / "TEST-card.xml"
    report.write_text('<testsuite name="CardTest" tests="2" failures="0" errors="0" skipped="0"><properties><property name="manaforge.revision" value="wrong"/></properties></testsuite>')
    engine = dict(sets_jars=[dict(sha256="hash")])
    assert backlog.verified_references(lock, tmp_path, engine) == {}
    report.write_text(report.read_text().replace('value="wrong"', 'value="expected"'))
    assert backlog.verified_references(lock, tmp_path, engine) == {"card.txt": ["CardTest"]}
    report.write_text(report.read_text().replace('failures="0"', 'failures="1"'))
    assert backlog.verified_references(lock, tmp_path, engine) == {}
    with pytest.raises(ValueError, match="different engine builds"):
        backlog.verified_references(lock, tmp_path, dict(sets_jars=[dict(sha256="other")]))


def test_saved_deck_priority_uses_oracle_identity_and_skips_display_copies(tmp_path):
    deck = dict(deck_id="deck", name="Saved", entries=[dict(name="Alias", oracle_id="oracle", section="commander", quantity=1), dict(name="Display", section="display_commander", quantity=1)])
    (tmp_path / "deck.manaforge.json").write_text(json.dumps(dict(deck=deck)))
    (tmp_path / "broken.manaforge.json").write_text("invalid")
    by_oracle, by_name, warnings = backlog.saved_deck_index(tmp_path)
    assert by_oracle == {"oracle": [dict(deck_id="deck", name="Saved")]}
    assert by_name == {}
    assert len(warnings) == 1
