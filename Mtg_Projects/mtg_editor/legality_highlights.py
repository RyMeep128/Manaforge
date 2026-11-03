"""Card-specific violations from the existing local deck checkers."""
from mtg_core.commander import check_commander
from mtg_core.legality import check_constructed


def card_violations(document, records):
    report = (check_commander(document, records) if document.deck.format == "Commander"
              else check_constructed(document, records))
    messages = {}
    for issue in report.issues:
        if issue.severity == "Error":
            for entry_id in issue.entry_ids:
                messages.setdefault(entry_id, []).append(issue.message)
    return {entry_id: "\n".join(dict.fromkeys(lines)) for entry_id, lines in messages.items()}
