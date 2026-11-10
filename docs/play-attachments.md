# Battlefield attachments

The gateway translates native attached-to and attachment lists into current opaque
public object references. It exports relationships only between identified public
battlefield cards or public players; missing/concealed relationships remain
unsupported rather than exposing private native identifiers.

The table groups attached Auras and Equipment under the permanent they belong to,
including across controllers. Player attachments sit beside the affected player.
Three attachment cards peek out from behind the host; the count badge opens the
whole family in the existing paged card browser. Each card retains its source
artwork, inspection, individual input and native tapped state. Changes to native
relationships restore the normal layout on detach or zone change. Unknown hosts
and cyclic relationships fall back to separate cards.

Arena's Core.dll was inspected read-only: GenerateAttachmentMap follows native
AttachedToId, battlefield stacks track their parent and attachment count, and
AttachmentAndExileStackBrowserProvider exposes grouped cards for inspection.
Those presentation patterns informed this implementation; no Arena code was copied.
CI covers opaque-reference projection, ownership differences, detach, player
attachments, concealment, malformed cycles and unknown hosts. Unity behavior
remains subject to the repository's hosted license requirement.
