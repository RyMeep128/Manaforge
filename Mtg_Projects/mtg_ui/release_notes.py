"""Bundled player-facing notes. Keep historical entries for skipped updates.

Newest releases come first; put the most useful changes first in each group.
Python data travels with the application without a network or packaging asset.
"""
from mtg_print.update_service import is_newer_version, UpdateCheckError


RELEASES = (
    {
        'version': '0.3.60-alpha.1',
        'summary': 'A little more discovery with every update. Get back to your decks with the highlights at a glance.',
        'features': [
            'See what’s new after an update, with highlights from any versions you skipped.',
            'Revisit update highlights anytime from Help → What’s New.',
        ],
        'improvements': ['Read update highlights even when you’re offline.'],
    },
)

GROUPS = (('features', 'New Features'), ('improvements', 'Improvements'), ('fixes', 'Fixes'))


def load_notes(current, previous=None, releases=RELEASES):
    """Select installed-version notes only, merging and deduplicating skipped releases.

    Invalid entries are ignored individually. Manual access shows the newest
    available entry at or below the installed version when exact notes are absent.
    """
    candidates = []
    for release in releases:
        try:
            version = release['version']
            if is_newer_version(version, current):
                continue
            if previous and not is_newer_version(version, previous):
                continue
            candidates.append(release)
        except (KeyError, TypeError, UpdateCheckError):
            continue
    from functools import cmp_to_key
    candidates.sort(key=cmp_to_key(lambda a, b:
        -1 if is_newer_version(a['version'], b['version']) else
        1 if is_newer_version(b['version'], a['version']) else 0))
    if not previous:
        candidates = candidates[:1]
    groups = {key: [] for key, _ in GROUPS}
    seen = set()
    for release in candidates:
        for key in groups:
            items = release.get(key, [])
            if not isinstance(items, (list, tuple)):
                continue
            for item in items:
                if isinstance(item, str) and item.strip():
                    identity = ' '.join(item.split()).casefold()
                    if identity not in seen:
                        seen.add(identity)
                        groups[key].append(item.strip())
    summary = candidates[0].get('summary', '') if candidates else ''
    return {
        'summary': summary if isinstance(summary, str) else '',
        'groups': groups,
        'versions': [item['version'] for item in candidates],
    }
