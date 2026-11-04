> Historical record, archived November 3, 2026. Commands, status claims, and
> acceptance notes below describe their original increment. Use the
> [documentation index](../README.md) and [current roadmap](../roadmap.md) for current guidance.

# Feedback #11: mulligan failure after thinking

The private report from 0.5.220-alpha.1 describes a crash after selecting
mulligan. Its diagnostics contain METADATA_IO_FAILED and older JSON_INVALID
errors. The matching local sessions lasted longer than one minute.

The active development branch still gave the authenticated metadata server a
60-second timeout between requests. Waiting at any choice, including mulligan,
closed this channel; the next metadata request failed the match. Bring the
integration branch's idle-aware frame reader onto development and use it for
metadata requests. The 60-second deadline now starts with the first frame byte.
Authentication, partial-frame deadlines, cancellation and cleanup stay bounded.
Do not reconnect or replay game commands after an uncertain submission.

An independent error-reporting bug sent orderly viewer EOF (null) into the JSON
parser, producing JSON_INVALID. Classify it as LIVE_UNITY_DISCONNECTED before
dispatch. This establishes one source of JSON_INVALID; it does not establish
that every older JSON_INVALID report was caused by EOF.

Regression coverage includes a real authenticated metadata client that waits
61 seconds between requests, then successfully makes two requests; orderly
viewer EOF; idle cancellation; and a partial frame that times out after an idle
wait. The metadata fixture's outer timeout is 90 seconds to accommodate this
regression. Existing malformed JSON corpus checks remain intact.

Validation is assigned to the existing Play protocol fixtures GitHub Actions
workflow. No local test suites were run, per AGENTS.md. Full Unity/XMage
mulligan replay and all historical JSON_INVALID failures remain unverified.
