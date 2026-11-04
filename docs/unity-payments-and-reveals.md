# Unity payments and revealed cards

Auto payment uses the native engine's legal mana productions and conditions. It considers mixed-color sources, eligible floating mana, and supported flexible or conditional sources. A bounded search chooses a covering plan with few activations, then revalidates each source against the current native payment context before submitting through the authenticated command path. It never activates sources to simulate a plan.

Life payments, sacrifice costs, X choices, unsupported effects/costs, uncertain conditions and relevant replacement/trigger hazards remain manual. Manual and Full Control payment modes remain manual. The payment panel displays the reason for falling back. An uncertain or failed automatic step is not retried. Retained session diagnostics include the native payment mode, reason and counters when available.

Public reveals are recorded as opaque observation groups before client snapshot coalescing. Unity presents every card in a group together, including its name when artwork cannot be resolved. Inspect enlarges individual cards. **I've seen these** acknowledges the current group and advances to the next. Repeated snapshots do not replay acknowledged observations; a new reveal has a new group identity.

Pending reveals block local gameplay commands and automatic priority passing. Native work already in flight can finish; acknowledgement is a local presentation gate rather than a fabricated rules action. Viewer/session changes and terminal state clear the queue and revoke artwork access. Historical observations do not become live game object references.

Regression suites must run through GitHub Actions against the committed SHA. Compilation and a Unity player build do not establish playable human-versus-AI or visual acceptance.
