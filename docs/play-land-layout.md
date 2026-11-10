# Land piles

Matching battlefield lands are displayed next to one another in piles of at most
two. Different printings of the same Oracle card can share a pile. Tapped and
untapped copies remain separate. Counters, attachments, animated lands, commander
identities and unknown visible state keep cards separate. Visible ability text,
current type, color, controller, owner and damage participate in matching.
Every card retains its own view, artwork, hit area and engine command reference.
The exposed rear card can be inspected or selected separately.

Land rows progressively shrink from their normal size to a 62-pixel minimum as
their land count grows, and then page by whole piles. Both players use the same
layout, preserving the space occupied by the player panel.

Arena's local Core.dll was inspected read-only: CanStackComparer delegates to
CardViewUtilities.CanStack, which compares card data, selection and interaction
state; battlefield layout variants expose card scale and stack limits. Manaforge
uses that state-aware grouping approach with the requested two-card maximum,
not a copied implementation or a claim that Arena uses these exact dimensions.
CI covers the pair limit, printing differences, tap state, counters, scaling,
individual object retention and whole-pile paging.
