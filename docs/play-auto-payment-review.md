# Auto payment review: Goblin Lackey versus Lifegain

The retained normal-game log from 2026-11-10 contains repeated REQUIRES_MANUAL
fallbacks. That establishes a real fallback, not a successful automatic cast.
The game finished normally, but payment totals were previously retained only
from error reports; normal game-result reports are now included as well.

The local Wizards reference was inspected read-only at
`Downloads/Assets from Wizards, given with permission/Managed/Core.dll`.
`PayCostsRequestHandler_AutoTap` validates matching request/response identifiers
and reads the rules engine's supplied auto-tap solutions. The client workflow
presents those solutions. This shows the client/engine boundary; the client
assembly does not establish the rules engine's payment-solving algorithm.
No Arena implementation or assets were copied into Manaforge.

Manaforge's native hazard screen treated characteristic-changing continuous
effects as payment hazards unless their primary layer was power/toughness or
color. It now allows ordinary continuous effects in characteristic layers 1–7,
whose results are already reflected by the native controller, ability, cost and
production queries. Rules-modifying effects are screened using their native
payment-event prefilter, like replacement effects and triggers. No applies or
checkTrigger methods are called during inspection. Unknown effects, cost
modifications, relevant mana events and consequential costs retain manual input.

CI adds Goblin Lackey with exactly one Mountain against Soul Warden, Soul's
Attendant and Voice of the Blessed, with Goblin King/Warchief registered in the
library, plus a Goblin Chieftain battlefield variant. Both require the native
spell on the stack, exactly one tapped Mountain and zero manual payment inputs.
They test cast/payment, not Lackey's combat-damage trigger. Active Manabarbs and
Mana Flare, insufficient mana and the existing double-red checks remain covered.
These fixtures represent the reported interaction; they are not a replay of the
unrecorded exact board or proof of every card in either saved deck.

Only GitHub Actions runs the suites. Compilation and a local player build are
not evidence that these behavioral regressions have passed.
