# Automatic mana payment

Auto payment is owned by the Java gateway and native engine. Unity does not
choose sources or implement mana rules. Manual and Full Control keep native
payment decisions. In Auto, eligible floating mana is usable automatically.

## Native planning and execution

`NativePaymentSearch` copies the game with `createSimulationForAI`, then replaces
all copied players with `PaymentSimulationPlayer` instances that have independent
response objects. Native activation and native `assignPayment` run only on those
copies. Pool items retain their conditions, source objects and snow provenance;
color totals never authorize a payment. The finalized unpaid cost is copied and
the full finalized cost remains available to native spending conditions.

A quick candidate sequence and a bounded best-first search seek complete native
payments. Ranking favors fewer activations and less excess mana; ties favor ordinary
lands over creatures and preserve more flexible sources where possible. The search
uses at most 100,000 candidate expansions and a cooperative 250 ms budget after
creating the initial isolated snapshot. A native operation already in progress
finishes before the next budget check. A complete verified candidate can be
returned when refinement reaches the budget. Exhaustion without a complete
candidate is distinct from insufficient mana and never taps a live source.

The server caches a plan only within the paused payment frame, game-state/cycle
and visible source list. Each first step has a private frame token and native
source ticket. Fresh legality, ability identity and source incarnation are
checked before native activation. Only recorded, still-legal mana-color answers
are replayed. Other decisions remain native player choices.

Execution receipts identify the exact payment frame and accepted native source
activation. Native cast/activation return values confirm completion, including
abilities that resolve without the stack. A tap or transport acknowledgement
alone does not prove payment. Changed pre-submit observations reject the local
attempt without replay; uncertain submitted responses are never retried.

## Coverage and manual boundaries

The native allocator handles colored, generic, colorless, hybrid, snow and
mana-paid Phyrexian costs. X, modes, targets, optional additional costs and the
native Phyrexian life alternative remain explicit choices. Auto pays their
finalized mana cost, including native cost adjustments and commander tax.

Supported source effects include native commander-identity/land-color helpers
and core fixed, conditional, chosen-color and
dynamic mana effects. Sources can be lands, rocks or creatures. Counters alone
are not a reason to reject a source. Native simulation handles deterministic
triggered mana additions such as mana doubling and mana-cost filters.

Auto does not pay life, take source-related damage, sacrifice, discard or remove
counters to generate mana. It rejects candidate sequences that change those
resources or queue a consequential non-mana trigger. An applicable harmful source
need not disable a different safe source. Unknown source effects, unreviewed
mana-event replacement effects, unresolved choices, mana-color-dependent spell
strategy and exhausted search budgets request manual input. These boundaries
are structural/native checks, with no card-name exceptions.

Private assessments distinguish READY, INSUFFICIENT_MANA,
CONSEQUENTIAL_CHOICE_REQUIRED, UNSUPPORTED_INTERACTION, SEARCH_LIMIT_REACHED and
STALE_CONTEXT. Reports retain bounded outcome counts rather than native source
IDs or private card data. The viewer protocol has no new payment solver API.

## CI and delivery evidence

The payment workflow runs stock compatibility and the exact delivery engine
from the app-owned engine lock. The delivery job requires the pinned Actions
archive digest, source SHA and both matching assembly hashes; no stock fallback
is allowed. Native runtime dependencies are checked against that bundle's
approved manifest. The source/artifact identity and native evidence are retained
as Actions logs/artifacts for the application SHA.

Tests exercise real native queries through the production automation wrapper,
coordinator, bridge command admission and response executor. The transport seam
uses native HumanPlayer response methods instead of a network socket. This
proves the production payment path inside real games, not Unity/network or
whole-match acceptance. Denizen/two Mountains, double-red and saved-deck Lackey
regressions remain, alongside cost/source matrices, safe/manual outcomes,
stackless abilities, seeded boards, restricted pools, exhaustive small-board
native sequences and live-state isolation checks.

Only GitHub Actions runs suites. Compilation is not behavioral acceptance.
Hosted Unity acceptance remains blocked until its license is configured. Rebuild
the local player after reviewing the relevant exact-SHA CI results, preserve the
previous player/logs and record application SHA plus engine bundle identity.
