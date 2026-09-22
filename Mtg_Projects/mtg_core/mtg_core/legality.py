"""Constructed deck checks based on local, dated Oracle legality records."""
import time
from .commander import Report, Issue, copy_limit, abilities, front, STALE_DAYS
from .companions import companion_restriction

FORMATS = ('Standard', 'Modern', 'Pauper', 'Legacy', 'Vintage')


def check_constructed(document, records, *, now=None):
    now = time.time() if now is None else now
    format_name = document.deck.format
    main = [e for e in document.deck.entries if e.section == 'mainboard']
    side = [e for e in document.deck.entries if e.section == 'sideboard']
    entries = main + side
    report = Report(sum(e.quantity for e in main))
    def issue(severity, code, message, selected=()):
        report.issues.append(Issue(severity, code, message, tuple(e.entry_id for e in selected)))
    if format_name not in FORMATS:
        issue('Unknown', 'format', 'Select a supported format to check legality; Custom has no enforced rules.')
        return report
    if report.total < 60:
        issue('Error', 'size', f'The main deck contains {report.total} cards; at least 60 are required.')
    if sum(e.quantity for e in side) > 15:
        issue('Error', 'sideboard', 'The sideboard exceeds 15 cards.', side)
    if any(e.section == 'commander' for e in document.deck.entries):
        issue('Error', 'commander_section', f'{format_name} does not use commanders; move those cards to the mainboard or sideboard.')
    payloads, groups, dates, stale, undated = {}, {}, [], [], []
    for entry in entries:
        record = records.get(entry.card_id, {})
        payload = record.get('payload', {'name': entry.name, **entry.extras.get('facts', {})})
        payloads[entry.entry_id] = payload
        groups.setdefault(str(payload.get('name') or entry.name).casefold(), []).append(entry)
        if entry.quantity < 1:
            issue('Error', 'quantity', f'{entry.name}: quantity must be positive.', [entry])
        status = (payload.get('legalities') or {}).get(format_name.casefold())
        if status not in ('legal', 'restricted'):
            issue('Error' if status in ('banned', 'not_legal') else 'Unknown', 'legality',
                  f'{entry.name}: {status or "unknown legality"} in local {format_name} data.', [entry])
        if status == 'restricted' and format_name != 'Vintage':
            issue('Unknown', 'legality', f'{entry.name}: unexpected restricted status for {format_name}.', [entry])
        cached = record.get('cached_at')
        if not cached or cached > now:
            undated.append(entry)
        else:
            dates.append(cached)
            if now - cached > STALE_DAYS * 86400:
                stale.append(entry)
    for group in groups.values():
        count = sum(e.quantity for e in group)
        if count <= 1:
            continue
        limits = [1 if (payloads[e.entry_id].get('legalities') or {}).get(format_name.casefold()) == 'restricted'
                  else copy_limit(payloads[e.entry_id], default=4) for e in group]
        if any(limit is None for limit in limits):
            issue('Unknown', 'copies', f'{group[0].name}: copy limit could not be verified.', group)
        elif count > min(limits):
            issue('Error', 'copies', f'{group[0].name}: {count} copies across main deck and sideboard; allowed {min(limits)}.', group)
    companion_id = document.deck.extras.get('companion_entry_id')
    if companion_id:
        companion = next((e for e in side if e.entry_id == companion_id), None)
        if companion is None or companion.quantity != 1:
            issue('Error', 'companion_selection', 'The selected companion must be one card in the sideboard.')
        else:
            payload = payloads[companion.entry_id]
            if not any(a.startswith('companion') for a in abilities(payload)):
                issue('Unknown' if front(payload).get('oracle_text') is None else 'Error', 'companion_ability', 'Companion ability not verified.', [companion])
            else:
                bad, unknown, explanation = companion_restriction(payload.get('name') or companion.name, main, payloads, commander=False)
                if bad:
                    issue('Error', 'companion_restriction', explanation, [e for e in main if e.entry_id in bad] or [companion])
                if unknown:
                    issue('Unknown', 'companion_restriction', explanation + ' Some characteristics need review.', [e for e in main if e.entry_id in unknown])
    for code, selected, message in [('stale', stale, f'Card data is older than {STALE_DAYS} days; refresh Core data.'),
                                     ('undated', undated, 'Cache date unavailable; current legality is unverified.')]:
        if selected:
            issue('Unknown', code, message, selected)
    report.oldest_cache = min(dates) if dates else None
    return report
