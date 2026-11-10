# Screenshot payment regression

The native-payment workflow includes two real XMage game fixtures: Foundry Street
Denizen (`{R}`) and Ember Hauler (`{R}{R}`), each with exactly two untapped Mountains
and opposing Wirewood Herald and Llanowar Elves. Both use actual native cards,
registered abilities, casting, the guarded ordinary-payment adapter, native mana
responses, stack verification, and resolution. The fixtures require one and two
Mountain taps respectively, without manually selected payment sources or any
opponent source use. Existing native hazard checks still reject mana-sensitive
triggers.

Real games register abilities for cards in hidden zones too. The fixtures include
inactive Manabarbs and Mana Flare in the opponent's library: their battlefield
abilities must not block payment or change mana production. A separate fixture
puts Manabarbs onto the battlefield and requires manual fallback with neither
Mountain tapped. The engine-side filter ignores only proven inactive battlefield
sources; delayed and pending triggers and unknown sources remain guarded.

These focused fixtures are not a networked Unity acceptance run. The separate
Java human-versus-AI workflow checks gateway gameplay; Unity visual acceptance is
reported separately and requires an activated editor in CI. Do not count API or
proxy-game helper checks alone as successful real-game payment.

The reported screenshot session used `0.6.13-alpha.1`, whose broad hazard filter
rejected unrelated battlefield triggers. The ordinary-payment event filter was
narrowed in `0.6.14-alpha.1`. Preserve retained session logs when rebuilding the
player, and record the exact verified source SHA beside the resulting build.
