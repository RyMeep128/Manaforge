"""Deck-local organization choices and stable quick-menu preferences."""
from dataclasses import dataclass
import uuid

from mtg_core.decks import DeckCategory
from .organization import assign, remove_category

STARTERS = ('Plan', 'Interact', 'Ramp', 'Draw')
MAX_RING = 8


@dataclass(frozen=True)
class TagChoice:
    key: str
    name: str
    tags: bool = False
    count: int = 0
    starter: bool = False


def unique_names(names):
    result, seen = [], set()
    for value in names:
        name = str(value).strip()
        if name and name.casefold() not in seen:
            result.append(name)
            seen.add(name.casefold())
    return result


def preferences(document):
    raw = document.editor_preferences.get('quick_menu', {})
    return raw if isinstance(raw, dict) else {}


def hold_delay(document):
    try:
        return max(150, min(1500, int(preferences(document).get('hold_delay', 250))))
    except (TypeError, ValueError):
        return 250


def choices(document, tags=False, *, active=True, configured=True):
    entries = [e for e in document.deck.entries if e.quantity > 0]
    result = []
    if tags:
        names = unique_names([*document.deck.tags, *(tag for e in entries for tag in e.tags)])
        for name in names:
            count = sum(e.quantity for e in entries if name.casefold() in {t.casefold() for t in e.tags})
            if count or not active:
                result.append(TagChoice('tag:' + name.casefold(), name, True, count))
    else:
        for category in sorted(document.deck.categories, key=lambda c: c.sort_order):
            count = sum(e.quantity for e in entries if category.category_id in e.category_ids)
            if count or not active:
                result.append(TagChoice(category.category_id, category.name, False, count))
        if not entries:
            names = unique_names(preferences(document).get('starters', STARTERS))
            for name in names:
                category = next((c for c in document.deck.categories if c.name.casefold() == name.casefold()), None)
                result.append(TagChoice(category.category_id if category else 'starter:' + name.casefold(),
                                        category.name if category else name, starter=category is None))
    # Legacy files can contain duplicate names; do not create duplicate wedges.
    seen, deduplicated = set(), []
    for choice in result:
        identity = choice.key if not active and not tags else choice.name.casefold()
        if identity not in seen:
            deduplicated.append(choice)
            seen.add(identity)
    result = deduplicated
    if not configured:
        return result
    order = preferences(document).get('tags_order' if tags else 'roles_order', [])
    positions = {key: i for i, key in enumerate(order)}
    return sorted(result, key=lambda c: positions.get(c.key, len(positions)))


def radial_choices(document, tags=False):
    options = choices(document, tags)
    hidden = set(preferences(document).get('tags_overflow' if tags else 'roles_overflow', []))
    ring = [c for c in options if c.key not in hidden][:MAX_RING]
    keys = {c.key for c in ring}
    return ring, [c for c in options if c.key not in keys]


def retain_tag_definitions(document):
    document.deck.tags = unique_names([*document.deck.tags,
        *(tag for entry in document.deck.entries for tag in entry.tags)])


def ensure_choice(document, name, tags=False):
    name = name.strip()
    if not name:
        raise ValueError('Enter a name.')
    if tags:
        retain_tag_definitions(document)
        existing = next((n for n in document.deck.tags if n.casefold() == name.casefold()), None)
        if existing is None:
            document.deck.tags.append(name)
        return existing or name
    category = next((c for c in document.deck.categories if c.name.casefold() == name.casefold()), None)
    if category is None:
        category = DeckCategory(str(uuid.uuid4()), name,
                               max((c.sort_order for c in document.deck.categories), default=-1) + 1)
        document.deck.categories.append(category)
        replace_preference_key(document, 'starter:' + name.casefold(), category.category_id)
    return category.category_id


def apply_choice(document, ids, name, tags=False, *, toggle=False):
    if not name and not tags:
        assign(document, ids, 'category', None)
        return
    value = ensure_choice(document, name, tags)
    entries = [e for e in document.deck.entries if e.entry_id in ids]
    if tags:
        remove = toggle and bool(entries) and all(value.casefold() in {t.casefold() for t in e.tags} for e in entries)
        for entry in entries:
            entry.tags = [t for t in entry.tags if t.casefold() != value.casefold()]
            if not remove:
                entry.tags.append(value)
    else:
        assign(document, ids, 'category', value)


def replace_preference_key(document, old, new):
    prefs = preferences(document)
    for key in ('roles_order', 'roles_overflow', 'tags_order', 'tags_overflow'):
        if key in prefs:
            prefs[key] = [new if value == old else value for value in prefs[key]]


def rename_choice(document, choice, name):
    name = name.strip()
    if not name:
        raise ValueError('Enter a name.')
    known = choices(document, choice.tags, active=False)
    if any(c.key != choice.key and c.name.casefold() == name.casefold() for c in known):
        raise ValueError('That name already exists. Choose a different name.')
    if choice.starter:
        prefs = document.editor_preferences.setdefault('quick_menu', {})
        prefs['starters'] = [name if n.casefold() == choice.name.casefold() else n
                            for n in prefs.get('starters', STARTERS)]
        replace_preference_key(document, choice.key, 'starter:' + name.casefold())
    elif choice.tags:
        retain_tag_definitions(document)
        document.deck.tags = [name if n.casefold() == choice.name.casefold() else n for n in document.deck.tags]
        for entry in document.deck.entries:
            entry.tags = [name if n.casefold() == choice.name.casefold() else n for n in entry.tags]
        replace_preference_key(document, choice.key, 'tag:' + name.casefold())
    else:
        next(c for c in document.deck.categories if c.category_id == choice.key).name = name
        if not document.deck.entries or 'starters' in preferences(document):
            prefs = document.editor_preferences.setdefault('quick_menu', {})
            prefs['starters'] = [name if n.casefold() == choice.name.casefold() else n
                                for n in prefs.get('starters', STARTERS)]


def delete_choice(document, choice):
    if choice.starter:
        prefs = document.editor_preferences.setdefault('quick_menu', {})
        prefs['starters'] = [n for n in prefs.get('starters', STARTERS) if n.casefold() != choice.name.casefold()]
    elif choice.tags:
        document.deck.tags = [n for n in document.deck.tags if n.casefold() != choice.name.casefold()]
        for entry in document.deck.entries:
            entry.tags = [n for n in entry.tags if n.casefold() != choice.name.casefold()]
    else:
        remove_category(document, choice.key)
        if not document.deck.entries or 'starters' in preferences(document):
            prefs = document.editor_preferences.setdefault('quick_menu', {})
            prefs['starters'] = [n for n in prefs.get('starters', STARTERS) if n.casefold() != choice.name.casefold()]
