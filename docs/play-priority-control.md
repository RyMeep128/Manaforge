# Priority controls

The active gameplay implementation is Unity. See [Unity priority passing](unity-priority-passing.md) for the researched behavior, controls, engine command flow, safety constraints, deployment requirements, and parity gaps.

The earlier version of this document described the legacy Qt priority controller, including Qt settings persistence and turn boundaries that were never part of Unity. Those descriptions are not evidence of Unity behavior. Unity now supports single passing, passing until response, turn yields, resolving a stack, temporary and persistent Full Control, and separate own/opponent phase and combat-step stops through the existing Unity policy.

XMage supplies every opportunity and legal action. Configuring a stop cannot create priority in a step where the engine grants none, and no yield can answer a mandatory non-priority choice.
