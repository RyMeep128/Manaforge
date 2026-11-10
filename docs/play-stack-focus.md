# Stack focus and Resolve All

New public stack objects expand the stack automatically. Expanded cards use the
full card/ability presentation, a dedicated backdrop and a short presentation hold
before automatic passing. View/Minimize changes only the local presentation.
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

CI covers stack-removal progression, empty-stack stopping, required choices,
new responses, failure, phase stops, manual restoration and focus-panel lifecycle.
Hosted Unity execution remains dependent on repository licensing.
