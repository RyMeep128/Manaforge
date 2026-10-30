# Keep-first London mulligan engine follow-up

Status: prepared source patch; **not applied to the bundled runtime**.

The pinned XMage `xmage_1.4.62V1` implementation bottoms cards during
`LondonMulligan.mulligan`, before the next Keep/Mulligan question. The UI cannot
change that order without answering engine decisions on the player's behalf.

[Prepared patch](../Mtg_Projects/mtg_play/engine_patches/london-keep-first.patch)
moves the existing bottom-selection loop to `endMulligan`, which the engine calls
when the player keeps (including a forced keep at zero). Redraw, shuffle, free
mulligan accounting, saved opening-hand size, copy behavior and player targeting
remain engine-owned. No deck document is changed. Smoothed London inherits this
behavior and needs its own verification.

Source: [pinned LondonMulligan.java](https://github.com/magefree/mage/blob/xmage_1.4.62V1/Mage/src/main/java/mage/game/mulligan/LondonMulligan.java).
Downloaded UTF-8 source SHA-256:
`abea450526a3ebcfe6d29c9a52656e474f79f8b6e60d9bb74639eb6083c5b80b`.
The patch passes `git apply --check` against that source. This does not establish
compilation, AI correctness or gameplay acceptance.

Before enabling this engine change:

- Build and test a declared patched runtime in CI. Record patch provenance and
  hashes in the runtime manifest; preserve verification of the upstream artifact.
  Do not silently substitute a modified class under the existing pinned identity.
- Exercise initial keep, one and repeated paid mulligans, multiplayer free
  mulligans, forced keep at zero, and modified starting hand sizes. Each redraw
  must offer Keep/Mulligan before any bottom selection; final keep must bottom
  exactly the accumulated paid count with the engine's ordering prompt.
- Verify human and AI seats, Smoothed London, copied game state, disconnect and
  cancellation during bottom selection. Assert no repeated bottom prompt after
  completion and no opponent hand disclosure in snapshots or diagnostics.
- Run the offline bridge's full opening-hand sequence against the patched
  engine, then manually review Keep/Mulligan and bottom selection in the app.

The current UI continues to display the actual runtime's offered decisions.
