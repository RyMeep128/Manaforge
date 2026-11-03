"""One-time private metadata provisioning for owned native game sessions."""

import json
import secrets
import time
import uuid

from . import connection_proof as transport


def provision_metadata(
    process, server_process, server, metadata_context, manifest_hash
):
    metadata_key = bytearray(secrets.token_bytes(32))
    try:

        def frame(value):
            payload = json.dumps(value).encode("utf-8")
            process.stdin.write(len(payload).to_bytes(4, "big") + payload)
            process.stdin.flush()

        def wait_private(path, seconds):
            deadline = time.monotonic() + seconds
            while not path.is_file():
                if (
                    process.poll() is not None
                    or server_process.poll() is not None
                    or time.monotonic() >= deadline
                ):
                    raise transport.ProofError("METADATA_STARTUP_FAILED")
                time.sleep(0.01)
            with path.open("rb") as source:
                payload = source.read(4097)
            if len(payload) > 4096:
                raise transport.ProofError("METADATA_STARTUP_INVALID")
            result = json.loads(payload)
            path.unlink()
            return result

        frame(dict(metadata_bootstrap_version=1, owner_key_hex=metadata_key.hex()))
        context = wait_private(metadata_context, 60)
        if set(context) != {"game", "player"} or any(
            not isinstance(context[field], str)
            or str(uuid.UUID(context[field])) != context[field]
            for field in context
        ):
            raise transport.ProofError("METADATA_STARTUP_INVALID")
        request_id = str(uuid.uuid4())
        # One-time private provisioning only. All later metadata queries are Java-to-Java.
        server_process.stdin.write(
            json.dumps(
                dict(
                    request_id=request_id,
                    command="start_metadata_channel",
                    **context,
                    owner_key_hex=metadata_key.hex(),
                    hash=manifest_hash,
                )
            )
            + "\n"
        )
        server_process.stdin.flush()
        address = wait_private(
            server / "manaforge-responses" / (request_id + ".json"), 10
        )
        if (
            set(address) != {"host", "port", "session"}
            or address["host"] != "127.0.0.1"
            or type(address["port"]) is not int
            or not 1 <= address["port"] <= 65535
            or not isinstance(address["session"], str)
            or not address["session"].startswith("metadata-")
        ):
            raise transport.ProofError("METADATA_STARTUP_INVALID")
        frame(address)
    finally:
        metadata_key[:] = bytes(len(metadata_key))
