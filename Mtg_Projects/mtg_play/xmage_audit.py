"""Complete read-only inventory built on xmage_support and the existing backlog index."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

from . import xmage_support as support
from .rules_identity import (
    canonical_cards,
    canonicalize_requests,
    engine_rule_name,
    name_key,
)

ROOT = Path(__file__).resolve().parents[2]


def load_cards(path, classify):
    """Aggregate every printing; never select an arbitrary GROUP BY payload."""
    cards = {}
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.execute("BEGIN")
        canonical = {
            oid: (name, layout)
            for oid, name, layout in db.execute(
                "SELECT oracle_id,name,layout FROM cards_oracle"
            )
        }
        for oid, name, code, set_name, payload in db.execute(
            "SELECT oracle_id,name,set_code,set_name,payload_json FROM prints ORDER BY oracle_id,card_id"
        ):
            card = json.loads(payload)
            row = cards.setdefault(
                oid,
                dict(
                    oracle_id=oid,
                    name=canonical.get(oid, (name,))[0],
                    layout=canonical.get(oid, (name, card.get("layout")))[1],
                    sets={},
                    set_categories={},
                    categories=set(),
                    legalities=set(),
                    keywords=set(),
                    token_dependencies=set(),
                    release_dates=set(),
                    novelty_markers=set(),
                ),
            )
            row["release_dates"].add(card.get("released_at", "unknown"))
            row["novelty_markers"].update(
                marker
                for marker, present in {
                    "silver": card.get("border_color") == "silver",
                    "acorn": card.get("security_stamp") == "acorn",
                    "playtest": "playtest" in card.get("promo_types", []),
                }.items()
                if present
            )
            row["sets"][code or "?"] = set_name or code or "?"
            kind = classify(card)
            row["categories"].add(kind)
            row["set_categories"].setdefault(code or "?", set()).add(kind)
            row["legalities"].add(
                card.get("legalities", {}).get("commander", "unknown")
            )
            row["keywords"].update(card.get("keywords", []))
            row["token_dependencies"].update(
                part["name"]
                for part in card.get("all_parts", [])
                if part.get("component") == "token"
            )
    for oid, (name, layout) in canonical.items():
        cards.setdefault(
            oid,
            dict(
                oracle_id=oid,
                name=name,
                layout=layout,
                sets={},
                set_categories={},
                categories={"non_game_or_unresolved"},
                legalities={"unknown"},
                keywords=set(),
                token_dependencies=set(),
                release_dates=set(),
                novelty_markers=set(),
            ),
        )
    for row in cards.values():
        row["category"] = next(
            (
                kind
                for kind in (
                    "paper_rules",
                    "novelty",
                    "token_dependency",
                    "digital_or_nonpaper",
                    "nonstandard_rules",
                    "non_game_or_unresolved",
                )
                if kind in row["categories"]
            ),
            "non_game_or_unresolved",
        )
        row["set_categories"] = {
            code: sorted(kinds) for code, kinds in sorted(row["set_categories"].items())
        }
        row["classification_evidence"] = sorted(row.pop("categories"))
        row["commander_legality"] = (
            "legal"
            if "legal" in row["legalities"]
            else "|".join(sorted(row["legalities"]))
        )
        row["legality_conflict"] = len(row.pop("legalities")) > 1
        for key in (
            "keywords",
            "token_dependencies",
            "release_dates",
            "novelty_markers",
        ):
            row[key] = sorted(row[key])
    return sorted(cards.values(), key=lambda r: (name_key(r["name"]), r["oracle_id"]))


def deck_inventory(directory, catalog_path, engine):
    decks, warnings, hashes = [], [], []
    from .setup import saved_decks

    # Use the application's discovery, which also includes migrated/local library decks.
    discovered, discovery_warnings = saved_decks(Path(directory).parent)
    paths = {str(d.path.resolve()): d.path for d in discovered if d.path}
    paths.update(
        {str(p.resolve()): p for p in Path(directory).glob("*.manaforge.json")}
    )
    warnings.extend(str(w) for w in discovery_warnings)
    sources = [(str(p), p, None) for p in sorted(paths.values())]
    sources += [(d.key, None, d.document.to_dict()) for d in discovered if not d.path]
    for source, path, cached_document in sources:
        before = (
            support.sha256(path)
            if path
            else hashlib.sha256(
                json.dumps(cached_document, sort_keys=True).encode()
            ).hexdigest()
        )
        try:
            document = (
                json.loads(path.read_text(encoding="utf-8-sig"))
                if path
                else cached_document
            )
            requests = support.deck_requests(document, source)
            requests = canonicalize_requests(
                requests,
                canonical_cards((r.get("oracle_id") for r in requests), catalog_path),
            )
            rows = support.compare(requests, engine)
            dependencies = [r for r in rows if r["status"] == "token_dependency"]
            unique = {}
            for row in rows:
                if row["status"] not in {"skipped", "token_dependency"}:
                    unique[row.get("oracle_id") or name_key(row.get("name") or "")] = (
                        row
                    )
            rows = sorted(unique.values(), key=lambda r: name_key(r.get("name") or ""))
            deck = document["deck"]
            decks.append(
                dict(
                    name=deck.get("name"),
                    format=deck.get("format"),
                    source=source,
                    token_dependencies=dependencies,
                    supported=sum(r["status"] == "available" for r in rows),
                    unsupported=sum(r["status"] != "available" for r in rows),
                    missing=[r for r in rows if r["status"] != "available"],
                    rules_availability_compatible=bool(rows)
                    and all(r["status"] == "available" for r in rows),
                    launch_compatible="not_verified: format/engine validation and launch not executed",
                )
            )
        except (ValueError, KeyError, TypeError) as error:
            warnings.append(f"{path}: {error}")
        if path and before != support.sha256(path):
            raise ValueError("Saved deck changed during audit: " + str(path))
        hashes.append(dict(path=source, sha256=before))
    return decks, warnings, hashes


def assemble(cards, engine, upstream, decks):
    compared = support.compare(cards, engine)
    usage = defaultdict(set)
    for deck in decks:
        for row in deck["missing"]:
            usage[row.get("oracle_id") or name_key(row["name"])].add(deck["name"])
            row["upstream_evidence"] = upstream.get(
                name_key(engine_rule_name(row["name"], row.get("oracle_id"))), []
            )
    for row in compared:
        evidence = upstream.get(
            name_key(engine_rule_name(row["name"], row["oracle_id"])), []
        )
        row.update(
            upstream_evidence=evidence,
            upstream_implemented=bool(evidence),
            identity_review_required=row["status"] == "identity_mismatch"
            or (row["status"] != "available" and " // " in row["name"]),
            behavior_verified=False,
            verification_scope="class availability only; no rules tests associated",
            saved_decks=sorted(usage[row["oracle_id"]] | usage[name_key(row["name"])]),
        )
        missing = row["status"] != "available"
        commander = (
            row["category"] == "paper_rules" and row["commander_legality"] == "legal"
        )
        row["priority"] = (
            (
                1
                if row["saved_decks"]
                else 2
                if commander and evidence
                else 3
                if commander
                else 4
                if row["category"] == "paper_rules"
                else 5
            )
            if missing
            else 0
        )
        row["work_kind"] = (
            "available_class_requires_behavior_verification"
            if not missing
            else "upstream_engine_update_candidate"
            if evidence
            else "identity_review"
            if row["status"] == "identity_mismatch"
            else "implementation_or_registration_investigation"
        )
        row["shared_dependency_candidates"] = row["keywords"] if missing else []
    sets = []
    grouped = defaultdict(list)
    for row in compared:
        for code in row["sets"]:
            kinds = row.get("set_categories", {}).get(code, [row["category"]])
            category = row["category"] if row["category"] in kinds else kinds[0]
            grouped[(code, category)].append(row)
    for (code, category), rows in sorted(grouped.items()):
        missing = [r["name"] for r in rows if r["status"] != "available"]
        if missing:
            sets.append(
                dict(
                    set_code=code,
                    set_name=rows[0]["sets"][code],
                    category=category,
                    total=len(rows),
                    supported=len(rows) - len(missing),
                    missing=len(missing),
                    coverage_percent=round(
                        100 * (len(rows) - len(missing)) / len(rows), 2
                    ),
                    missing_names=missing,
                )
            )
    sets.sort(key=lambda r: (-r["missing"], r["set_code"], r["category"]))
    counts = dict(
        unique_cards=len(compared),
        supported=sum(r["status"] == "available" for r in compared),
        missing=sum(r["status"] != "available" for r in compared),
        missing_commander_legal=sum(
            r["status"] != "available"
            and r["category"] == "paper_rules"
            and r["commander_legality"] == "legal"
            for r in compared
        ),
    )
    counts["missing_by_category"] = dict(
        sorted(
            Counter(
                r["category"] for r in compared if r["status"] != "available"
            ).items()
        )
    )
    counts["missing_by_status"] = dict(
        sorted(
            Counter(r["status"] for r in compared if r["status"] != "available").items()
        )
    )
    counts["missing_paper_upstream"] = sum(
        r["status"] != "available"
        and r["category"] == "paper_rules"
        and r["upstream_implemented"]
        for r in compared
    )
    return dict(counts=counts, cards=compared, sets=sets, decks=decks)


def write(output, report):
    output.mkdir(parents=True, exist_ok=False)
    (output / "audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    missing = [r for r in report["cards"] if r["status"] != "available"]
    dependencies = defaultdict(list)
    for row in missing:
        for keyword in row["shared_dependency_candidates"]:
            dependencies[keyword].append(row["name"])
    tables = {
        "dependency-candidates": [
            dict(
                keyword=k,
                count=len(v),
                cards=v,
                evidence="Scryfall keyword only; missing engine mechanic not established",
            )
            for k, v in sorted(dependencies.items())
        ],
        "cards": report["cards"],
        "missing": missing,
        "sets": report["sets"],
        "decks": report["decks"],
        "commander-missing": [
            r
            for r in missing
            if r["category"] == "paper_rules" and r["commander_legality"] == "legal"
        ],
        "novelty-missing": [r for r in missing if r["category"] == "novelty"],
        "upstream-missing": [r for r in missing if r["upstream_implemented"]],
        "backlog": sorted(
            missing, key=lambda r: (r["priority"], name_key(r["name"]), r["oracle_id"])
        ),
    }
    for name, rows in tables.items():
        with (output / (name + ".csv")).open(
            "w", encoding="utf-8-sig", newline=""
        ) as stream:
            fields = list(rows[0]) if rows else ["name"]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        k: support.csv_value(
                            json.dumps(v, ensure_ascii=False, sort_keys=True)
                            if isinstance(v, (list, dict))
                            else v
                        )
                        for k, v in row.items()
                    }
                )
    lines = [
        "# XMage coverage audit",
        "",
        "Scope: local catalog snapshot; available classes do not certify rules correctness. Missing includes unresolved identities and generated dependencies.",
        "",
        "```json",
        json.dumps(report["provenance"], indent=2),
        "```",
        "",
        "```json",
        json.dumps(report["counts"], indent=2),
        "```",
        "",
        "## Sets with missing ordinary paper cards",
        "",
        "| Set | Name | Eligible | Available | Missing | Coverage |",
        "|---|---|---:|---:|---:|---:|",
    ]
    lines += [
        f"| {r['set_code']} | {r['set_name']} | {r['total']} | {r['supported']} | {r['missing']} | {r['coverage_percent']}% |"
        for r in report["sets"]
        if r["category"] == "paper_rules"
    ]
    lines += [
        "",
        "Each Oracle ID counts once globally and once within each set containing a printing. Reprints count in every such set; set totals must not be summed for global counts.",
        "",
        "## Missing Commander-legal cards",
        "",
    ]
    lines += [
        f"- {r['name']} ({', '.join(sorted(r['sets']))}); {r['status']}; upstream: {r['upstream_implemented']}"
        for r in tables["commander-missing"]
    ]
    lines += [
        "",
        "## Saved decks",
        "",
        "| Deck | Format | Available | Unsupported | Rules available | Missing |",
        "|---|---|---:|---:|---|---|",
    ]
    lines += [
        f"| {r['name']} | {r['format']} | {r['supported']} | {r['unsupported']} | {r['rules_availability_compatible']} | {', '.join(x['name'] for x in r['missing'])} |"
        for r in report["decks"]
    ]
    lines += [
        "",
        "Launch compatibility is not certified: this read-only audit does not execute engine format validation or matches. Keyword groups are dependency candidates, not proof a mechanic is absent. Token rows measure catalog/class evidence, not engine-generated token correctness.",
        "",
        "## Recommendation",
        "",
        "Resolve saved-deck blockers first; then review an upstream update for Commander cards with source registrations. Implement remaining Commander cards in mechanic batches after confirming engine support. No popularity score is used.",
        "",
        "## Input warnings",
        "",
        *report["warnings"],
    ]
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(classify, upstream_index):
    from mtg_core.paths import data_root
    from .connection_proof import DEFAULT_BUNDLE, DEFAULT_JDK

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", action="store_true")
    parser.add_argument(
        "--catalog", type=Path, default=support.configured_catalog(data_root())
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--upstream", default="upstream/master")
    parser.add_argument("--saved-decks", type=Path, default=data_root() / "decks")
    parser.add_argument("--server-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    server = args.server_dir or support.find_server(
        ROOT / "Mtg_Projects/mtg_play", DEFAULT_BUNDLE
    )
    java = DEFAULT_JDK / "bin/java.exe"
    if not java.exists():
        java = shutil.which("java")
    print("Reading pinned engine catalog...", flush=True)
    engine, metadata = support.read_engine_catalog(
        server, java, ROOT / "tools/java/XmageCatalogProbe.java"
    )
    lock = json.loads((ROOT / "Mtg_Projects/mtg_play/engine-lock.json").read_text())
    if any(
        r["sha256"] not in lock["artifacts"].values() for r in metadata["sets_jars"]
    ):
        raise ValueError("Installed sets JAR does not match app engine lock")
    revision, upstream = upstream_index(args.source, args.upstream)
    before = support.sha256(args.catalog)
    cards = load_cards(args.catalog, classify)
    decks, warnings, hashes = deck_inventory(args.saved_decks, args.catalog, engine)
    if before != support.sha256(args.catalog):
        raise ValueError("Catalog changed during audit")
    report = assemble(cards, engine, upstream, decks)
    today = datetime.now(timezone.utc).date().isoformat()
    report["counts"]["missing_paper_future_release_only"] = sum(
        r["category"] == "paper_rules"
        and r["status"] != "available"
        and bool(r["release_dates"])
        and min(r["release_dates"]) > today
        for r in report["cards"]
    )
    report.update(
        provenance=dict(
            generated_at=datetime.now(timezone.utc).isoformat(),
            manaforge_commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            working_tree_diff_sha256=__import__("hashlib")
            .sha256(subprocess.check_output(["git", "diff", "HEAD"], cwd=ROOT))
            .hexdigest(),
            catalog_path=str(args.catalog),
            catalog_sha256=before,
            upstream_commit=revision,
            engine_lock_sha256=support.sha256(
                ROOT / "Mtg_Projects/mtg_play/engine-lock.json"
            ),
            engine_revision=lock["fork_commit"],
            engine_bundle_id=lock.get("bundle_id"),
            engine=metadata,
            saved_deck_hashes=hashes,
        ),
        warnings=warnings,
        report_version=1,
    )
    write(args.output, report)
    print(json.dumps(report["counts"], indent=2))
