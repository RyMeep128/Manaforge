"""Small module registry; no tool imports or startup side effects."""
from dataclasses import dataclass


def module_available(module):
    """Use the same workspace availability in source and installed builds."""
    return module.available


@dataclass(frozen=True)
class Module:
    key: str
    title: str
    description: str
    icon: str
    action: str
    available: bool = True


MODULES = (
    Module('editor', 'Deck Editor', 'Build, organize, and refine your Magic decks.', 'cards', 'editor'),
    Module('rules', 'Rules & Rulings', 'Explore Magic rules, card information, and rulings.', 'book', 'rules'),
    Module('print', 'Print Studio', 'Prepare custom proxies, print sheets, and PDF exports.', 'printer', 'printer'),
    Module('library', 'Browse Online', 'Join friend libraries, browse shared decks, and copy them to My Decks.', 'book', 'library'),
    Module('play', 'Play', 'Play with friends or against AI using your saved decks.', 'swords', 'play'),
)
