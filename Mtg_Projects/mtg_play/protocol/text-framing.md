# Play text framing v1 — G1 transport foundation

Status: shared Java/C# framing and local fixtures implemented; no sockets,
authentication, JSON envelope parser or dummy process exchange yet. Existing
Python/Qt gameplay and engine pins are unchanged.

Each frame is four bytes of unsigned big-endian payload length, followed by
exactly that many UTF-8 bytes. The length range is 1 through 1,048,576 bytes,
checked before payload allocation. Empty streams represent orderly EOF; EOF
within a header or payload is an error. Multiple frames may be concatenated;
network packet boundaries have no meaning. The reader consumes one frame at a
time and does not read ahead into the next frame.

UTF-8 must decode strictly, with no replacement for malformed sequences or
surrogates. A leading UTF-8 BOM is rejected. Writers validate/encode before
emitting any bytes; encoded byte count, rather than character count, determines
the cap. Write/flush scheduling belongs to the transport, not the codec.

Failures contain only FRAME_SIZE, FRAME_TRUNCATED, FRAME_UTF8 or FRAME_BOM.
Underlying I/O failures propagate to the owner and must receive sanitized error
mapping there. Do not log raw payloads, stream exceptions, tokens or deck data.
After a framing failure, close the connection; never attempt resynchronization.
A failed underlying write can be partial and does not authorize replay.

The synchronous codecs leave streams open and do not implement cancellation,
timeouts, backpressure or writer synchronization. Future transport workers must
own bounded deadlines, close streams to unblock cancellation, serialize writes
and keep these operations off Unity's rendering thread. Bound queued message
count/total bytes as well as individual frames. No codec call is authentication.

This layer accepts text, not validated JSON. JSON object-only envelopes, maximum
depth, duplicate-key rejection, unknown-field/version policy, ownership/seat
authorization, revision/decision freshness and acknowledgement semantics remain
required. Never pass decoded text directly into live gameplay dispatch. The
framing version is documented here and in fixtures; it is not an established
handshake field or the existing GAME_PROTOCOL_VERSION. Negotiate the actual
versioned protocol before accepting session data.

Java `manaforge.protocol.TextFrame` and C# `Manaforge.Play.Protocol.TextFrame`
consume `fixtures/text-frames-v1.json`: four positive streams and nine malformed
streams, each tested with normal and single-byte reads. Both test writers also
check exact maximum size and rejection of empty/oversized/malformed/BOM strings
without emitting bytes. UTF-8 multibyte text cannot bypass the byte cap.

Run `python tools/check_play_java_protocol.py` and
`./tools/unity-play.ps1 -Mode EditMode`. The Java helper uses the existing
hash-pinned Gson dependency for fixture parsing only; the codec itself needs
only the Java standard library. Existing DTO/launch checks run unchanged.
The hosted protocol workflow already invokes this helper, so its next run checks
Java framing too. Unity checks still require the licensed workflow/host.

Local results: Java shared-corpus and boundary checks passed; 28 Unity EditMode
checks passed. CI evidence remains pending. This is the first stream-boundary
piece for G1, not a completed dummy exchange or protocol freeze. Next implement
shared bounded JSON envelopes and rejection semantics, then authenticated
loopback/bootstrap exchange and shutdown with dummy peers. No bulk XMage port
is authorized by this increment.
