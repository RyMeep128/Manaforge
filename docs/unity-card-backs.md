# Shared card backs and future sleeves

`ICardBackProvider` resolves a shared texture using the owning player ID, never a card identity. `ClassicCardBackProvider` loads the bundled classic Magic back once; Unity owns that imported resource. Custom providers own their textures, while `CardBackView` only borrows them. A missing texture leaves the neutral component background.

Arena composition injects the provider into the viewer surface, piles, browser, hidden hand fan and draw animations. Other layouts can use the same components and provider. The generic theme Back helper delegates to the component. No network fetch or hidden-card artwork lookup occurs during gameplay.

Future sleeves implement the provider and rebind components when an owner's selection changes. This change adds no sleeve picker, persistence or wire fields. Size, shape and borders belong to shared component styles; hand layout retains its existing fan geometry and 12-card display bound.

Empty libraries show an empty pile. Unknown counts remain unknown. Hidden fans reuse children across snapshots and clear borrowed bindings when their count shrinks. Admitted face-down cards and hidden-zone rows show backs; authorized faces and missing-artwork placeholders remain distinct. Concealment clears private text, tooltips and face textures before a back appears. Face-down cards do not open face inspection. Authorized transformed faces retain their actual face.

Source attribution is bundled in `Resources/CardBack-NOTICE.txt`. The proxy-printing back remains unchanged. Run regression suites through GitHub Actions; compilation/build and synthetic visual captures are separate evidence from live playable acceptance.
