"""Explicit EDHREC theme associations, independent of card recommendation scores.

Commander frontend pages contain ``tag_counts`` (also exposed as
``panels.taglinks``). These are source-provided commander/theme memberships,
not the card recommendation categories in ``cardlists``. Pair cohorts remain
pairs; their counts must never be attributed to either commander alone.
"""

from contextlib import closing
from pathlib import Path
import re
import sqlite3

from .edhrec import commander_key


def normalize_discovery(payload, resolve, slug):
    card = payload["container"]["json_dict"]["card"]
    name = card["name"]
    identity = resolve(name)
    identities = [identity] if identity else [resolve(n) for n in name.split(" // ")]
    if not 1 <= len(identities) <= 2 or not all(identities) or len(set(identities)) != len(identities):
        raise ValueError(f"Unresolved commander: {name}")
    sample = card["num_decks"]
    if type(sample) is not int or sample < 0:
        raise ValueError("Invalid commander sample")
    tags = payload.get("tag_counts")
    if tags is None:
        tags = payload.get("panels", {}).get("taglinks")
    if not isinstance(tags, list):
        raise ValueError("No explicit EDHREC theme associations in this response")
    themes = {}
    for tag in tags:
        theme, title, count = tag["slug"], tag["value"], tag["count"]
        if not isinstance(theme, str) or not re.fullmatch(r"[a-z0-9-]+", theme):
            raise ValueError("Invalid theme slug")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Invalid theme name")
        if type(count) is not int or not 0 <= count <= sample:
            raise ValueError("Invalid theme cohort count")
        row = dict(slug=theme, name=title, count=count)
        if theme in themes and themes[theme] != row:
            raise ValueError("Conflicting theme associations")
        themes[theme] = row
    return dict(key=commander_key(identities), identities=sorted(identities),
                name=name, slug=slug, sample=sample, themes=list(themes.values()))


def save_discovery_page(path, data, imported):
    """Write one validated cohort to a staging snapshot, atomically."""
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS themes (
                slug TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS commanders (
                commander_key TEXT PRIMARY KEY, name TEXT NOT NULL,
                slug TEXT NOT NULL, sample INTEGER NOT NULL, imported REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS commander_members (
                commander_key TEXT REFERENCES commanders ON DELETE CASCADE,
                oracle_id TEXT NOT NULL, PRIMARY KEY(commander_key, oracle_id));
            CREATE TABLE IF NOT EXISTS theme_commanders (
                theme_slug TEXT REFERENCES themes, commander_key TEXT REFERENCES commanders ON DELETE CASCADE,
                num_decks INTEGER NOT NULL, PRIMARY KEY(theme_slug, commander_key));
            PRAGMA user_version=1;
        """)
        db.execute("INSERT OR REPLACE INTO commanders VALUES (?, ?, ?, ?, ?)",
                   (data["key"], data["name"], data["slug"], data["sample"], imported))
        db.executemany("INSERT INTO commander_members VALUES (?, ?)",
                       [(data["key"], oid) for oid in data["identities"]])
        for theme in data["themes"]:
            db.execute("INSERT INTO themes VALUES (?, ?) ON CONFLICT(slug) DO UPDATE SET name=excluded.name",
                       (theme["slug"], theme["name"]))
            db.execute("INSERT INTO theme_commanders VALUES (?, ?, ?)",
                       (theme["slug"], data["key"], theme["count"]))


class DiscoveryStore:
    """Read-only snapshot access. Missing data never triggers collection."""

    def __init__(self, path):
        self.path = Path(path)

    def snapshot(self, theme=None, *, should_cancel=None):
        if not self.path.exists():
            return dict(themes=[], members=[], status="EDHREC theme data unavailable. Local commander search is available.")
        from .search.cancellation import check_cancelled

        check_cancelled(should_cancel)
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.1)) as db:
            db.row_factory = sqlite3.Row
            if should_cancel:
                db.set_progress_handler(lambda: int(should_cancel()), 1000)
            db.execute("BEGIN")
            if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("Unsupported EDHREC discovery snapshot version")
            themes = []
            for row in db.execute(
                "SELECT t.slug, t.name, count(tc.commander_key) AS cohorts FROM themes t "
                "JOIN theme_commanders tc ON tc.theme_slug=t.slug GROUP BY t.slug ORDER BY t.name COLLATE NOCASE"):
                check_cancelled(should_cancel)
                themes.append(dict(row))
            members = []
            if theme:
                for row in db.execute(
                    "SELECT c.*, tc.num_decks, m.oracle_id FROM theme_commanders tc "
                    "JOIN commanders c USING(commander_key) JOIN commander_members m USING(commander_key) "
                    "WHERE tc.theme_slug=? ORDER BY tc.num_decks DESC, c.commander_key, m.oracle_id", (theme,)):
                    check_cancelled(should_cancel)
                    members.append(dict(row))
            count, imported = db.execute("SELECT count(*), max(imported) FROM commanders").fetchone()
        check_cancelled(should_cancel)
        return dict(themes=themes, members=members, imported=imported,
                    status=f"Offline EDHREC themes from {count} cached commander cohorts; coverage is limited to imported pages. Counts belong to each exact cohort, not global theme totals."
                    if themes else "No EDHREC theme associations in the local snapshot. Local commander search is available.")
