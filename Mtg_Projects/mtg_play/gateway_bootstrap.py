"""Private gateway-only framing. No JSON interpretation or viewer delivery."""

MAX_GATEWAY_BOOTSTRAP_BYTES = 1024 * 1024


class GatewayBootstrapError(ValueError):
    pass


def frame_gateway_manifest(payload):
    """Return a caller-owned mutable frame for bounded writing and subsequent clearing.

    Input must be the trusted exporter's immutable bytes. Java validates the full
    native manifest/pin contract; framing does not imply authentication/readiness.
    """
    if (
        not isinstance(payload, bytes)
        or not 1 <= len(payload) <= MAX_GATEWAY_BOOTSTRAP_BYTES
    ):
        raise GatewayBootstrapError("GATEWAY_BOOTSTRAP_INVALID")
    frame = bytearray(4 + len(payload))
    frame[:4] = len(payload).to_bytes(4, "big")
    frame[4:] = payload
    return frame
