"""Built-in color identities; browsing never changes deck legality."""
from PyQt6 import QtWidgets as W

COLOR_GROUPS = (
    ('Mono Color', [('White', 'W'), ('Blue', 'U'), ('Black', 'B'), ('Red', 'R'), ('Green', 'G'), ('Colorless', '')]),
    ('Two Colors', list(zip(('Azorius', 'Dimir', 'Rakdos', 'Gruul', 'Selesnya', 'Orzhov', 'Izzet', 'Golgari', 'Boros', 'Simic'),
                           ('WU', 'UB', 'BR', 'RG', 'WG', 'WB', 'UR', 'BG', 'WR', 'UG')))),
    ('Three Colors', list(zip(('Esper', 'Grixis', 'Jund', 'Naya', 'Bant', 'Abzan', 'Jeskai', 'Sultai', 'Mardu', 'Temur'),
                             ('WUB', 'UBR', 'BRG', 'WRG', 'WUG', 'WBG', 'WUR', 'UBG', 'WBR', 'URG')))),
    ('Four Colors', [(f'Without {name}', colors) for name, colors in
                     [('White', 'UBRG'), ('Blue', 'WBRG'), ('Black', 'WURG'), ('Red', 'WUBG'), ('Green', 'WUBR')]]),
    ('Five Colors', [('Five-Color', 'WUBRG')]),
)
SYMBOLS = {'W': '\u2600', 'U': '\U0001f4a7', 'B': '\U0001f480', 'R': '\U0001f525', 'G': '\U0001f333'}


def color_combo():
    combo = W.QComboBox()
    combo.setAccessibleName('Color identity')
    combo.addItem('Any color identity', None)
    for group, options in COLOR_GROUPS:
        combo.addItem(group)
        combo.model().item(combo.count() - 1).setEnabled(False)
        for name, colors in options:
            symbols = ' '.join(SYMBOLS[c] for c in colors) or '\u25c7'
            combo.addItem(f'{symbols}  {name} ({colors or "C"})', colors)
    return combo
