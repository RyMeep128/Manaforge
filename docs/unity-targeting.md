# Shared targeting presentation

Native `ContextHumanPlayer` captures target-selection parameters only for the lifetime of a native choose-target call. Its metadata probe requires the response lock, open response, matching payer, game and cycle. Non-target choices are excluded with the engine's `isNotTarget` flag. Source, limits and selected targets for the current native target group are projected into nullable `ChoiceRequest.targeting`; missing context keeps the existing choice controls.

`GameSnapshot.stack_targets` carries viewer-safe source/target relationships and completeness from native stack metadata. Player targets are supported. Targets that cannot be mapped into the current viewer snapshot are omitted and completeness is false. Repeated targets are retained. Incomplete stack lists do not invent target numbering. These values are presentation data, never command permissions.

`TargetingState` supplies immutable presentation data; `ViewerTargetingController` binds current card/player anchors and existing authenticated choice methods. The passive `TargetingOverlay`, outline children and shared theme draw source emphasis, cyan legal targets, gold hover endpoints, green selected targets and numbered/amount markers. Layouts compose the controller and register their player panels; they do not calculate targeting legality.

Engine-offered face-down cards use generic labels and back anchors; their identities remain hidden.

Click/Enter retains the existing option path. Drag from the source (or the prompt when the source is unavailable) onto a legal target to submit that same current option. Invalid drops do nothing; stale offers cancel drags; pending commands reject duplicates. Escape cancels a drag first and otherwise cancels only a cancellable current choice. Ambiguous card options remain explicit through the existing action list/menu. Native confirmed selections drive markers; there is no local staged selection or fabricated undo.

Hover/focus a stack object to inspect confirmed targets. Active targeting takes precedence, while combat retains its own renderer. Geometry follows current visible anchors on each UI update. Hidden/off-screen/removed endpoints are not inferred. Yield status remains compact while hovering stack targets, and required targeting decisions remain manual. Reveals continue to gate submission. Reduced motion removes outline transitions; cursor tracking is immediate.

The schema additions are optional-valued fields emitted by all matching DTOs. Generated clients, schemas, baseline/negative fixtures and API inventory are updated together; an old client must not be mixed with the new gateway. Run suites through GitHub Actions only. Builds, compilation and synthetic screenshots are not playable human-versus-AI acceptance.
