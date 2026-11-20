"""Owned host/guest launch. Network callbacks carry only the invited seat's bootstrap."""

import json
import os
import re
from pathlib import Path
import secrets
import time
import uuid
from dataclasses import replace
from .recovery import HostRecovery, RecoveryMailbox, atomic_json
from . import connection_proof as transport
from .contracts import ADAPTER_VERSION
from .deck_preview import DEFAULT_PLAYER
from .launch_lifecycle import LaunchOwner
from .launch_manifest import export_launch_manifest
from .live_game import LiveGameError, resolve_rules_manifest, validate_close_report
from .native_metadata import provision_metadata
from .public_artwork import PublicArtworkServer
from .runtime_distribution import owned
from .session_logs import network_timing_summary
from .viewer_bootstrap import export_viewer_bootstrap


def _raise_game_error(root):
    errors = [root / "game-error.json"]
    if root.name == "seat-0":
        errors.append(root.parent / "game-error.json")
    for error in errors:
        if error.is_file():
            code = "MULTIPLAYER_ENGINE_FAILED"
            try:
                if error.stat().st_size <= 8192:
                    candidate = json.loads(error.read_text(encoding="utf-8")).get(
                        "code"
                    )
                    if isinstance(candidate, str) and re.fullmatch(
                        r"[A-Z_0-9]{1,100}", candidate
                    ):
                        code = candidate
            except (OSError, ValueError, AttributeError):
                pass
            raise LiveGameError(code)


def wait_json(root, name, cancel, process=None, seconds=120):
    path = root / (name + ".json")
    deadline = time.monotonic() + seconds
    while not path.is_file():
        if (
            cancel.is_set()
            or process is not None
            and process.poll() is not None
            or time.monotonic() >= deadline
        ):
            raise LiveGameError("MULTIPLAYER_STARTUP_FAILED")
        _raise_game_error(root)
        time.sleep(0.02)
    if path.stat().st_size > 16384:
        raise LiveGameError("MULTIPLAYER_READY_INVALID")
    return json.loads(path.read_text(encoding="utf-8"))


def player_command(root, player, acceptance=False):
    command = [
        str(player),
        "-screen-fullscreen",
        "0",
        "-screen-width",
        "1280",
        "-screen-height",
        "720",
        "-logFile",
        str(root / "player.log"),
        "-manaforgeLiveGame",
        str(root),
    ]
    if acceptance:
        command += ["-manaforgeGameAcceptance", "1", "-manaforgeNoCapture", "1"]
    return command


def watch_player(owner, root, cancel, report, recovery=None):
    ready = wait_json(root, "game-ready", cancel, seconds=120)
    if ready != {"live_game_version": 1, "authenticated": True}:
        raise LiveGameError("UNITY_GAME_READY_INVALID")
    owner.client_ready()
    report({"phase": "Unity multiplayer game running"})
    deadline = time.monotonic() + 21600
    while owner.client_exit_code is None:
        if recovery is not None:
            recovery.tick()
        if cancel.wait(0.05):
            return {"outcome": None, "interrupted": True}
        if time.monotonic() >= deadline:
            raise LiveGameError("UNITY_GAME_SESSION_TIMEOUT")
        _raise_game_error(root)
        gateway = owner.gateway_process
        if gateway is not None and gateway.poll() is not None:
            raise LiveGameError("GAME_INTERRUPTED")
    _raise_game_error(root)
    if owner.client_exit_code != 0:
        raise LiveGameError("UNITY_GAME_PLAYER_FAILED")
    closed = wait_json(root, "game-closed", cancel, seconds=5)
    validate_close_report(closed)
    return closed


def prepare_manifest(manifest, server_process, server, cancel):
    def request(command):
        request_id = str(uuid.uuid4())
        server_process.stdin.write(
            json.dumps({**command, "request_id": request_id}) + "\n"
        )
        server_process.stdin.flush()
        value = wait_json(
            server / "manaforge-responses",
            request_id,
            cancel,
            server_process,
            seconds=30,
        )
        (server / "manaforge-responses" / (request_id + ".json")).unlink()
        return value

    from .rules_identity import canonical_cards

    canonical = canonical_cards(
        e.get("oracle_id")
        for s in manifest["seats"]
        for e in s["document"]["deck"]["entries"]
    )
    resolved = resolve_rules_manifest(manifest, request, canonical)
    for seat in resolved["seats"]:
        deck = seat["document"]["deck"]
        designated = set(deck["commander_entry_ids"])

        def row(e):
            return dict(
                name=e["name"],
                set=e["set_code"].upper(),
                number=e["collector_number"],
                quantity=e["quantity"],
            )

        cards = [
            row(e)
            for e in deck["entries"]
            if e["section"] == "mainboard" and e["entry_id"] not in designated
        ]
        side = [
            row(e)
            for e in deck["entries"]
            if e["section"] == "commander"
            or e["entry_id"] in designated
            or e["section"] == "sideboard"
            and resolved["format"] != "unrestricted_commander"
        ]
        if (
            request(
                dict(
                    command="validate_deck",
                    format=resolved["format"],
                    cards=cards,
                    sideboard=side,
                )
            ).get("eligible")
            is not True
        ):
            raise LiveGameError("UNITY_GAME_DECK_INVALID")
    return resolved


@owned
def run_host_game(
    setup,
    documents,
    cancel,
    report,
    *,
    version,
    launch,
    remote_prepare,
    remote_finished=None,
    payment_modes=("auto", "auto"),
    player=DEFAULT_PLAYER,
    xmage_root=None,
    jdk_path=transport.DEFAULT_JDK,
    acceptance=False,
    recovery_mailbox=None,
):
    if len(setup.seats) != 2 or setup.seats[0].controller != "local_human" or setup.seats[1].controller not in ("local_human", "engine_ai"):
        raise LiveGameError("MULTIPLAYER_SETUP_UNSUPPORTED")
    if any(mode not in ("auto", "manual", "full-control") for mode in payment_modes):
        raise LiveGameError("PAYMENT_MODE_INVALID")
    if xmage_root is None:
        from .engine_fork import selected_bundle

        xmage_root = selected_bundle(
            transport.HERE / "mage-full_1.4.62-dev_2026-10-03_20-47"
        )
    from .engine_fork import manifest_digest

    pin = manifest_digest(xmage_root)
    initial_ai = setup.seats[1].controller == "engine_ai"
    engine_setup = replace(setup, seats=tuple(replace(seat, controller="local_human") for seat in setup.seats))
    payload = export_launch_manifest(
        engine_setup, documents, manaforge_version=version, engine_bundle=xmage_root
    )
    manifest = json.loads(payload)
    player = Path(player).resolve()
    if not player.is_file():
        raise LiveGameError("UNITY_GAME_BUILD_MISSING")
    launch.allocate()
    result = None

    def consume(first, events, peers, port, server_process, server):
        nonlocal result
        report({"phase": "Validating both players' decks"})
        resolved = prepare_manifest(manifest, server_process, server, cancel)
        root = launch.root
        local_root = root / "seat-0"
        local_root.mkdir()
        artwork = PublicArtworkServer(
            local_root,
            manifest["manifest_id"] + "-" + setup.seats[0].seat_id,
            setup.seats[0].seat_id,
        )
        owner = launch.owner = LaunchOwner(
            startup_timeout=120,
            runtime_cleanup=lambda: (
                transport.stop_process(server_process, "shutdown").get("reaped") is True
            ),
        )
        keys = [bytearray(secrets.token_bytes(32)), bytearray(secrets.token_bytes(32))]
        try:
            owner.start_gateway(
                [
                    str(Path(xmage_root) / "java/jre1.8.0_201/bin/java.exe"),
                    "-Djava.awt.headless=true",
                    "-Dfile.encoding=UTF-8",
                    "-Djava.net.preferIPv4Stack=true",
                    "-Dmanaforge.adapterVersion=" + ADAPTER_VERSION,
                    "-Dmanaforge.multiplayer=true",
                    "-Dmanaforge.publicArtwork="
                    + str(local_root / "artwork/manifest.json"),
                    "-cp",
                    str(server.parent / "classes") + os.pathsep + str(server / "lib/*"),
                    "ManaforgeLiveGame",
                    str(port),
                    pin,
                    str(root / "gateway-ready.json"),
                    str(root / "unused-metadata.json"),
                ],
                cwd=str(root),
                launch_manifest=json.dumps(resolved, separators=(",", ":")).encode(),
                expect_manifest_validation=True,
            )
            owner.wait_gateway_manifest_validation(timeout=30)
            gateway = owner.gateway_process
            secret = json.dumps(
                {
                    "viewer_keys": [k.hex() for k in keys],
                    "payment_modes": [
                        m.upper().replace("-", "_") for m in payment_modes
                    ],
                }
            ).encode()
            gateway.stdin.write(len(secret).to_bytes(4, "big") + secret)
            gateway.stdin.flush()
            for index in range(2):
                provision_metadata(
                    gateway,
                    server_process,
                    server,
                    root / ("metadata-context-" + str(index) + ".json"),
                    pin,
                )
            ready = wait_json(root, "gateway-ready", cancel, gateway)
            addresses = ready.get("seats")
            if not isinstance(addresses, list) or len(addresses) != 2:
                raise LiveGameError("MULTIPLAYER_READY_INVALID")
            owner.gateway_ready()
            remote = addresses[1]
            remote_payload = {
                    "type": "prepare",
                    "format": setup.format,
                    "session_id": remote["session_id"],
                    "viewer_id": remote["viewer_id"],
                    "engine_version": "1.4.62-V1",
                    "artifact_manifest_sha256": pin,
                    "viewer_key_hex": keys[1].hex(),
                    "organization_version": 4,
                    "recovery_version": 1,
                }
            recovery = HostRecovery(
                root, server_process, server, gateway, cancel, report,
                recovery_mailbox or RecoveryMailbox(), remote_payload,
                lambda payload: remote_prepare(payload, remote["port"]),
                initial_ai=initial_ai,
            )
            atomic_json(local_root / "recovery-role.json", {"host": True})
            if not initial_ai:
                remote_prepare(remote_payload, remote["port"])
            local = addresses[0]
            owner.start_client(
                player_command(local_root, player, acceptance),
                cwd=str(player.parent),
                viewer_bootstrap=export_viewer_bootstrap(
                    port=local["port"],
                    session_id=local["session_id"],
                    viewer_id=local["viewer_id"],
                    engine_version="1.4.62-V1",
                    artifact_manifest_sha256=pin,
                    viewer_key=keys[0],
                    format=setup.format,
                    organization_version=4,
                    artwork_directory=artwork.directory,
                    artwork_manifest_sha256=artwork.pin,
                ),
            )
            result = watch_player(owner, local_root, cancel, report, recovery)
            if os.environ.get("MANAFORGE_NETWORK_TIMING") == "1":
                result["network_timing"] = network_timing_summary(root)
            if (
                result.get("outcome") in ("win", "loss", "draw")
                and remote_finished is not None
                and recovery.state.controller == "human"
                and recovery.state.connected
            ):
                report(
                    {
                        "phase": "Game finished. Waiting for the other player to close Unity."
                    }
                )
                while not remote_finished.wait(0.1) and not cancel.is_set():
                    if gateway.poll() is not None:
                        break
        finally:
            owner.close()
            artwork.close()
            for key in keys:
                key[:] = bytes(len(key))

    try:
        report({"phase": "Preparing host XMage engine"})
        proof = transport.run_proof(
            Path(xmage_root),
            Path(jdk_path),
            runtime_consumer=consume,
            cancel=cancel,
            payment_context_probe=True,
        )
        if not proof.get("success"):
            raise LiveGameError("MULTIPLAYER_RUNTIME_FAILED")
        return result
    finally:
        launch.close()


@owned
def run_guest_game(
    prepare, port, cancel, report, *, launch, player=DEFAULT_PLAYER, acceptance=False
):
    # No engine install, process, remote path, or remote executable is consulted.
    player = Path(player).resolve()
    if not player.is_file():
        raise LiveGameError("UNITY_GAME_BUILD_MISSING")
    launch.allocate()
    root = launch.root
    owner = launch.owner = LaunchOwner(startup_timeout=120)
    artwork = None
    try:
        artwork = PublicArtworkServer(root, prepare["session_id"], prepare["viewer_id"])
        bootstrap = export_viewer_bootstrap(
            port=port,
            session_id=prepare["session_id"],
            viewer_id=prepare["viewer_id"],
            engine_version=prepare["engine_version"],
            artifact_manifest_sha256=prepare["artifact_manifest_sha256"],
            viewer_key=bytes.fromhex(prepare["viewer_key_hex"]),
            format=prepare["format"],
            organization_version=prepare.get("organization_version"),
            artwork_directory=artwork.directory,
            artwork_manifest_sha256=artwork.pin,
        )
        owner.use_remote_gateway()
        if prepare.get("recovery_version") == 1:
            atomic_json(root / "recovery-role.json", {"host": False})
            atomic_json(root / "recovery-state.json", {"paused": True, "ended": False})
        owner.start_client(
            player_command(root, player, acceptance),
            cwd=str(player.parent),
            viewer_bootstrap=bootstrap,
        )
        result = watch_player(owner, root, cancel, report)
        if os.environ.get("MANAFORGE_NETWORK_TIMING") == "1":
            result["network_timing"] = network_timing_summary(root)
        return result
    finally:
        if artwork:
            artwork.close()
        launch.close()
