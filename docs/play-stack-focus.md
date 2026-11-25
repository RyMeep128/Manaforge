# Stack focus and Resolve All

New public stack objects expand the stack automatically. Expanded cards use the
full card/ability presentation and a dedicated backdrop. Stack focus and decorative
animations do not delay automatic passing. View/Minimize changes only the local presentation.
Emptying the stack removes the focus panel. Larger stacks retain paging.

Resolve All starts an explicit viewer-local priority yield. It submits the one
engine-offered pass action for each fresh priority decision, through the existing
authenticated command/receipt owner. It never resolves a stack object locally,
picks a target, pays a cost, grants consent or changes the rules engine.

The yield survives stack removals, pauses for required choices and phase stops,
and cancels on a newly added stack object, command failure, disconnect or game
over. It stops at an empty-stack decision instead of yielding beyond the stack.
Cancel remains available, and prior Manual control is restored on completion.

The local Arena Core.dll was inspected read-only. StackCardHolder maintains
card counts, docked state and an explicit ViewStack browser; its mediator
relayouts on stack modifications. These observations informed presentation only.
No Arena implementation or assets were copied. Resolve All uses Manaforge's
existing native priority authority, not an inferred Arena rules implementation.

Local Unity validation covers stack-removal progression, empty-stack stopping, required choices,
new responses, failure, phase stops, manual restoration and focus-panel lifecycle.
Run Unity checks and the Windows player build with `tools/validate_unity_local.ps1`;
non-Unity checks remain on GitHub Actions. See [priority passing](unity-priority-passing.md)
for the current fast-flow controls and acceptance requirements.
