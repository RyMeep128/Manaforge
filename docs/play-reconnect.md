# Two-player reconnect and seat takeover

The existing two-player battlefield is unchanged. The host's application owns
the running XMage match and must remain open. Host migration is not supported.

When a guest disconnects, the game pauses. The host can add MAD AI at skill 10,
end the game for everyone without a winner, or inspect the battlefield while it
remains paused. Resume Game becomes available once the replacement controller
is ready. Adding AI or reconnecting never automatically resumes a paused match.

Guests can select Reconnect after losing their connection, or enter the same
invitation after restarting Manaforge. Joining an active room shows both seats,
connection/controller status, life and commander names. Only the disconnected
guest seat or an AI opponent can be claimed. Anyone holding the invite may claim
it without host approval. A claim inherits the existing deck and game state.

The host serializes claims and issues fresh viewer credentials. Old connections
and queued messages cannot claim the replacement connection's credentials.
Gameplay receipts remain associated with the original seat across reconnects.

The updated relay advertises `recovery_version: 1` during admission. Deploy the
updated relay together with clients and the rebuilt gameplay runtime; older
relays are rejected. The relay remains transport-only: pending joiners receive
host-supplied public seat summaries, never gameplay broadcasts.

Validation is hosted in the multiplayer relay, Python, protocol, native
two-viewer and Unity workflows. Native coverage includes pausing an actual
human choice, handing it to MAD, returning to human control, and retaining seat
identity and state. These checks complement full playable acceptance; a successful
compile or player build alone does not establish gameplay acceptance.
