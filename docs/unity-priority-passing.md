# Automatic priority in Unity

This implementation targets the active Unity Arena gameplay path. It supersedes the earlier Qt-only priority patch for normal matches.

The top-right Unity priority panel starts with **Auto-pass with no responses** checked and **Manual control** unchecked. No phase or step stops are selected. Settings and temporary yields belong to the current viewer/session; a new game starts fresh.

Ordinary automatic passing waits 350 ms, then submits the current engine-provided pass action only when this is a genuine priority opportunity and the engine's complete action list contains no non-pass action. Available actions (including mana activations) and incomplete information preserve the prompt. Empty rendered controls alone never prove there is nothing to do.

- **Manual control** cancels a yield and holds every priority opportunity until unchecked.
- **Yield / phase stops** expands the controls; automation pauses while they are open.
- **Yield until my next turn** explicitly permits passing available responses until the viewer's next turn begins.
- **Yield until stack changes** explicitly permits passing available responses until stack membership or order changes. Opaque stack references remain stable while continuously present and retire on removal.
- **Cancel yield** ends the explicit yield; the ordinary auto-pass checkbox still applies.
- Phase and step stops apply on both players' turns and override all automatic modes.
- Rejected, uncertain, or failed commands pause automation. **Resume automatic passing** allows reconsideration of a fresh decision; an already-attempted decision is never automatically retried.

Targets, combat assignments, payments, trigger ordering, numeric input, and other non-priority choices remain manual. Existing authenticated offer identity, command tracking, and native submission validation remain authoritative. Late command failures are monitored even after the displayed offer is replaced. Viewer changes, completion, disconnect, and disposal cancel pending automation/yields. Engine desktop phase-skipping preferences are disabled so Unity receives priority opportunities needed for stops and manual control.

Validation: all Unity runtime C# scripts compiled against the installed Unity assemblies; 26 focused C# policy checks passed using the production projection and policy code. Seventeen native-to-Unity boundary checks passed, covering incomplete/filtered action lists, non-priority decisions and stack-reference lifetime/order. The updated Java bridge compiled. Eighty-six affected launch/adapter regressions passed on Python 3.13. Unity visual/player acceptance and full suites remain for CI; no CI run was awaited.

Changes are uncommitted on `feature/feedback-6-through-10`, alongside the feedback fixes. No installed application, Unity player, release or tag was changed. Rebuild/install the Unity player before testing this feature through the installed application.
