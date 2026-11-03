"""Triage local Core cards against an engine report, upstream registrations and Forge references."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Mtg_Projects"), str(ROOT / "Mtg_Projects/mtg_core")]
from mtg_core.paths import data_root  # noqa: E402
from mtg_play.xmage_support import configured_catalog, csv_value, name_key  # noqa: E402
from mtg_play.rules_identity import engine_rule_name  # noqa: E402

MECHANICS = {
    "f/feather_radiant_arbiter.txt": ["noncreature_cast_trigger", "legal_creature_choices", "optional_scaled_payment", "retargeted_spell_copies", "permanent_spell_tokens"],
    "i/immortal_obligation.txt": ["opponent_graveyard_reanimation", "enter_with_counter", "object_incarnation", "counter_bound_duration", "goad", "attack_and_block_restrictions"],
    "name:hit it!": ["controlled_haste", "public_library_reveal", "mandatory_land_selection", "tapped_entry", "graveyard_movement_not_milling"],
    "m/mjolnir_hammer_of_thor.txt": ["worthy_equip_filter", "equipped_damage_replacement", "enter_damage", "channel"],
}


def saved_deck_index(directory):
    by_oracle, by_name, warnings = {}, {}, []
    for path in sorted(Path(directory).glob("*.manaforge.json")):
        try:
            deck = json.loads(path.read_text(encoding="utf-8-sig"))["deck"]
            reference = dict(deck_id=deck["deck_id"], name=deck["name"])
            for entry in deck["entries"]:
                if entry.get("section", "mainboard") not in {"mainboard", "commander", "sideboard"} or entry.get("quantity", 1) <= 0:
                    continue
                if entry.get("oracle_id"):
                    by_oracle.setdefault(entry["oracle_id"], []).append(reference)
                elif entry.get("name"):
                    by_name.setdefault(name_key(entry["name"]), []).append(reference)
        except (OSError, ValueError, KeyError, TypeError) as error:
            warnings.append(dict(source=str(path), error=type(error).__name__))
    return by_oracle, by_name, warnings


def category(card):
    layout = card.get("layout", "")
    kind = card.get("type_line", "")
    if "Token" in kind or layout in {"token", "double_faced_token", "emblem"}:
        return "token_dependency"
    if layout in {"art_series", "reversible_card"} or not kind or "Card" == kind or "Card //" in kind:
        return "non_game_or_unresolved"
    if card.get("digital") or "paper" not in card.get("games", []):
        return "digital_or_nonpaper"
    if card.get("border_color") == "silver" or card.get("security_stamp") == "acorn" or card.get("set_type") == "funny":
        return "novelty"
    return "paper_rules"


def upstream_index(source, revision):
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", revision + "^{commit}"], text=True).strip()
    result = subprocess.run(["git", "-C", str(source), "grep", "-n", "SetCardInfo(\"", revision, "--", "Mage.Sets/src/mage/sets"], capture_output=True, encoding="utf-8", check=False)
    if result.returncode not in (0, 1):
        raise ValueError(result.stderr)
    files = set(subprocess.check_output(["git", "-C", str(source), "ls-tree", "-r", "--name-only", revision, "--", "Mage.Sets/src/mage/cards"], encoding="utf-8").splitlines())
    index = {}
    for line in result.stdout.splitlines():
        code = line.split(":", 3)[-1].lstrip()
        if code.startswith(("//", "*", "/*")):
            continue
        match = re.search(r'SetCardInfo\("([^"\\]*(?:\\.[^"\\]*)*)".*?([\w.]+)\.class', line)
        if match and "Mage.Sets/src/" + match.group(2).replace(".", "/") + ".java" in files:
            name = match.group(1).replace('\\"', '"')
            index.setdefault(name_key(name), []).append(dict(source=line.split("SetCardInfo", 1)[0].strip(), class_name=match.group(2)))
    return revision, index


def verified_references(lock_path, junit_directory, coverage_engine):
    if not lock_path or not junit_directory:
        return {}
    lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    expected_sets = {value for key, value in lock["artifacts"].items() if "/mage-sets-" in key}
    if not any(row["sha256"] in expected_sets for row in coverage_engine["sets_jars"]):
        raise ValueError("Coverage and verification use different engine builds")
    suites = {}
    for path in Path(junit_directory).glob("TEST-*.xml"):
        suite = ET.parse(path).getroot()
        properties = {p.get("name"): p.get("value") for p in suite.findall("./properties/property")}
        if properties.get("manaforge.revision") != lock["fork_commit"]:
            continue
        suites[suite.get("name")] = int(suite.get("tests", "0")) > 0 and all(int(suite.get(k, "0")) == 0 for k in ("errors", "failures", "skipped"))
    verified = {}
    for change in lock["local_changes"]:
        selected = [name for name in suites if fnmatch.fnmatchcase(name, change["tests"])]
        if selected and all(suites[name] for name in selected):
            if change.get("reference"):
                verified[change["reference"]] = sorted(selected)
            if change.get("card_name"):
                verified["name:" + name_key(change["card_name"])] = sorted(selected)
    return verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--upstream", default="upstream/master")
    parser.add_argument("--forge", type=Path, default=Path.home() / "ForgeMTG")
    parser.add_argument("--catalog", type=Path, default=configured_catalog(data_root()))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine-lock", type=Path, help="Pin for associating behavioral evidence with this engine build")
    parser.add_argument("--junit", type=Path, help="Focused engine Surefire reports; requires --engine-lock")
    parser.add_argument("--saved-decks", type=Path, default=data_root() / "decks", help="Read-only saved-deck usage for backlog priority")
    args = parser.parse_args()
    if bool(args.engine_lock) != bool(args.junit):
        parser.error("--engine-lock and --junit must be supplied together")
    report = json.loads(args.coverage.read_text(encoding="utf-8"))
    verified = verified_references(args.engine_lock, args.junit, report["engine"])
    deck_oracles, deck_names, deck_warnings = saved_deck_index(args.saved_decks)
    covered = {name_key(row["name"]): row for row in report["results"]}
    revision, upstream = upstream_index(args.source, args.upstream)
    references = {}
    archive = args.forge / "res/cardsfolder/cardsfolder.zip"
    with zipfile.ZipFile(archive) as scripts:
        for path in scripts.namelist():
            if not path.endswith(".txt"):
                continue
            raw = scripts.read(path)
            match = re.search(r"^Name:(.+)$", raw.decode("utf-8-sig"), re.MULTILINE)
            if match:
                references[name_key(match.group(1).strip())] = dict(path=path, sha256=hashlib.sha256(raw).hexdigest())
    rows = []
    with sqlite3.connect(args.catalog.resolve().as_uri() + "?mode=ro", uri=True) as db:
        for oracle_id, name, payload, code in db.execute("SELECT oracle_id,name,payload_json,set_code FROM prints GROUP BY oracle_id ORDER BY set_code,name"):
            card = json.loads(payload)
            key = name_key(name)
            coverage = covered.get(key, {})
            status = coverage.get("status")
            if status == "available":
                state = "catalog_and_class_present"
            elif name_key(engine_rule_name(name, oracle_id)) in upstream:
                state = "already_implemented_upstream"
            elif status == "identity_mismatch":
                state = "identity_mismatch"
            elif status == "missing_card":
                state = "missing_card"
            else:
                state = "unresolved"
            reference = references.get(key)
            tests = (verified.get(reference["path"], []) if reference else []) or verified.get("name:" + key, [])
            tested = state == "catalog_and_class_present" and bool(tests)
            if tested:
                state = "implemented"
            usage = deck_oracles.get(oracle_id, []) + deck_names.get(key, [])
            usage = list({item["deck_id"]: item for item in usage}.values())
            kind = category(card)
            priority = 0 if tested else 1 if kind == "paper_rules" and usage else 2 if kind == "paper_rules" and state == "already_implemented_upstream" else 3 if kind == "paper_rules" else 4 if kind == "token_dependency" else 5
            mechanics = (MECHANICS.get(reference["path"], []) if reference else []) or MECHANICS.get("name:" + key, [])
            rows.append(dict(oracle_id=oracle_id, name=name, engine_name=engine_rule_name(name, oracle_id), engine_name_candidates=coverage.get("engine_name_candidates", []), set_code=code, category=kind, status=state, verified=tested, verification_scope="engine_rules_tests" if tested else None, owner_review="pending", priority=priority, saved_deck_references=usage, required_mechanics=mechanics, dependencies=[], forge_reference=reference, upstream_evidence=upstream.get(name_key(engine_rule_name(name, oracle_id)), []), regression_tests=tests, notes="Registered implementation exercised by card tests" if tested else "Runtime instantiation and behavioral tests required before verified status"))
    rows.sort(key=lambda row: (row["priority"], row["set_code"].upper(), name_key(row["name"]), row["oracle_id"]))
    args.output.mkdir(parents=True, exist_ok=False)
    result = dict(backlog_version=2, upstream_commit=revision, engine=report["engine"], input_warnings=deck_warnings, forge_build=(args.forge / "build.txt").read_text().strip(), forge_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), rows=rows)
    (args.output / "backlog.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (args.output / "paper-missing.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["oracle_id", "name", "set_code", "category", "status", "verified"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows({key: csv_value(value) for key, value in row.items()} for row in rows if row["category"] == "paper_rules" and row["status"] not in {"catalog_and_class_present", "implemented"})
    counts = Counter((row["category"], row["status"]) for row in rows)
    summary = "\n".join(f"{kind}: {state}: {count}" for (kind, state), count in sorted(counts.items()))
    (args.output / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
