"""Owned saved-deck Unity session. Python handles startup/lifetime, never game decisions."""

import json
import os
import re
from pathlib import Path
import secrets
import shutil
import tempfile
import time
import uuid

from . import connection_proof as transport
from .contracts import ADAPTER_VERSION
from .deck_preview import DEFAULT_PLAYER
from .launch_lifecycle import LaunchOwner
from .launch_manifest import export_launch_manifest
from .native_metadata import provision_metadata
from .viewer_bootstrap import export_viewer_bootstrap


class LiveGameError(ValueError):
    pass


def validate_close_report(closed):
    if (
        closed.get("viewer_cleared") is not True
        or closed.get("cleanup_confirmed") is not True
        or closed.get("uncertain") != 0
    ):
        raise LiveGameError("UNITY_GAME_RESULT_UNCERTAIN")
    if closed.get("outcome") is None and closed.get("user_requested") is not True:
        raise LiveGameError("UNITY_GAME_ENDED_WITHOUT_RESULT")


def validate_scenario_close_report(closed, certificate, expected):
    if (
        closed.get("viewer_cleared") is not True
        or closed.get("cleanup_confirmed") is not True
        or closed.get("uncertain") != 0
        or certificate.get("scenario") != expected
        or certificate.get("native_commander_scenario_verified") is not True
    ):
        raise LiveGameError("UNITY_COMMANDER_SCENARIO_UNPROVEN")


def project_launch(setup, documents, version, deck_owners=None, *, engine_bundle=None):
    if (
        setup.format not in ("freeform", "commander")
        or len(setup.seats) != 2
        or sorted(s.controller for s in setup.seats) != ["engine_ai", "local_human"]
    ):
        raise LiveGameError("UNITY_GAME_SETUP_UNSUPPORTED")
    payload = export_launch_manifest(
        setup,
        documents,
        manaforge_version=version,
        deck_owners=deck_owners,
        engine_bundle=engine_bundle,
    )
    launch = json.loads(payload)
    for seat in launch["seats"]:
        if (
            setup.format == "freeform"
            and seat["document"]["deck"]["commander_entry_ids"]
        ) or seat["document"]["deck"]["companion_entry_id"] is not None:
            raise LiveGameError("UNITY_GAME_SETUP_UNSUPPORTED")
        if setup.format == "commander" and not (
            seat["document"]["deck"]["commander_entry_ids"]
            or any(
                e["section"] == "commander" for e in seat["document"]["deck"]["entries"]
            )
        ):
            raise LiveGameError("UNITY_GAME_SETUP_UNSUPPORTED")
        for entry in seat["document"]["deck"]["entries"]:
            if (
                not entry["name"]
                or not entry["set_code"]
                or not entry["collector_number"]
            ):
                raise LiveGameError("UNITY_GAME_CARD_UNSUPPORTED")
    return payload


def resolve_rules_manifest(manifest, server_request, canonical=None):
    """Resolve engine rules independently of saved artwork, without changing source decks."""
    from .rules_identity import engine_rule_name

    resolved = json.loads(json.dumps(manifest))
    for seat in resolved["seats"]:
        entries = seat["document"]["deck"]["entries"]
        canonical = canonical or {}
        queries = [
            dict(
                key=str(i),
                name=engine_rule_name(
                    canonical.get(e.get("oracle_id"), {}).get("name", e["name"]),
                    e.get("oracle_id"),
                ),
                set="",
                number="",
            )
            for i, e in enumerate(entries)
        ]
        response = server_request(dict(command="resolve_rules", cards=queries))
        if not isinstance(response, list) or len(response) != len(entries):
            raise LiveGameError("UNITY_GAME_CARD_RESOLUTION_FAILED")
        by_key = {}
        for row in response:
            if not isinstance(row, dict) or row.get("key") in by_key:
                raise LiveGameError("UNITY_GAME_CARD_RESOLUTION_FAILED")
            by_key[row.get("key")] = row
        for i, entry in enumerate(entries):
            row = by_key.get(str(i), {})
            if row.get("error"):
                raise LiveGameError("UNITY_GAME_CARD_UNSUPPORTED")
            if not all(
                isinstance(row.get(k), str) and row[k]
                for k in ("name", "set", "number")
            ):
                raise LiveGameError("UNITY_GAME_CARD_RESOLUTION_FAILED")
            # Only the private engine projection changes. card_id/oracle_id still
            # identify the deck's artwork; authenticated visibility is unchanged.
            entry.update(
                name=row["name"], set_code=row["set"], collector_number=row["number"]
            )
    return resolved


class LiveGameLaunch:
    def __init__(self):
        self.owner = None
        self.root = None
        self._identity = None
        self.summary = None
        self.last_error = None
        self.client_errors = []

    def allocate(self):
        self.root = Path(tempfile.mkdtemp(prefix="manaforge-live-game-"))
        self._parent = self.root.parent.resolve()
        stat = self.root.stat()
        self._identity = (stat.st_dev, stat.st_ino)

    def close(self):
        if self.owner is not None and not self.owner.close().confirmed:
            raise LiveGameError("UNITY_GAME_CLEANUP_UNCONFIRMED")
        if self.root is not None:
            resolved = self.root.resolve()
            if (
                self.root.is_symlink()
                or getattr(self.root, "is_junction", lambda: False)()
                or resolved.parent != self._parent
                or not resolved.name.startswith("manaforge-live-game-")
            ):
                raise LiveGameError("UNITY_GAME_FILES_CLEANUP_FAILED")
            if resolved.exists():
                stat = resolved.stat()
                if (stat.st_dev, stat.st_ino) != self._identity:
                    raise LiveGameError("UNITY_GAME_FILES_CLEANUP_FAILED")
                try:
                    log = resolved / "player.log"
                    if (
                        log.is_file()
                        and not log.is_symlink()
                        and log.stat().st_size <= 2 * 1024 * 1024
                    ):
                        diagnostic = log.read_text(encoding="utf-8", errors="replace")
                        self.client_errors = list(
                            dict.fromkeys(
                                re.findall(
                                    r"(?m)^([A-Za-z][A-Za-z0-9.]*Exception)(?=:|\r?$)|^\s*(?:at )?(Manaforge\.Play\.[A-Za-z0-9_.+<>]+)\s*\(",
                                    diagnostic,
                                )
                            )
                        )
                        self.client_errors = [
                            next(value for value in match if value)
                            for match in self.client_errors
                        ][-12:]
                except OSError:
                    pass
                try:
                    summary = resolved / "game-closed.json"
                    if (
                        summary.is_file()
                        and not summary.is_symlink()
                        and summary.stat().st_size <= 16384
                    ):
                        value = json.loads(summary.read_text(encoding="utf-8"))
                        self.summary = {
                            key: value.get(key)
                            for key in (
                                "outcome",
                                "snapshots",
                                "confirmed",
                                "uncertain",
                                "viewer_cleared",
                                "cleanup_confirmed",
                            )
                        }
                    error = resolved / "game-error.json"
                    if not error.is_file():
                        error = resolved / "game-unsupported.json"
                    if (
                        error.is_file()
                        and not error.is_symlink()
                        and error.stat().st_size <= 1024
                    ):
                        code = json.loads(error.read_text(encoding="utf-8")).get("code")
                        unsupported = resolved / "game-unsupported.json"
                        if (
                            code == "LIVE_OPENING_PROJECTION_UNSUPPORTED"
                            and unsupported.is_file()
                            and unsupported.stat().st_size <= 1024
                            and not unsupported.is_symlink()
                        ):
                            code = json.loads(
                                unsupported.read_text(encoding="utf-8")
                            ).get("code")
                        if isinstance(code, str) and re.fullmatch(
                            r"[A-Z_0-9]{1,100}", code
                        ):
                            self.last_error = code
                except (OSError, ValueError):
                    pass
                shutil.rmtree(resolved)
            self.root = None


def run_live_game(
    setup,
    documents,
    cancel,
    report,
    *,
    version,
    launch=None,
    player=DEFAULT_PLAYER,
    payment_mode="auto",
    deck_owners=None,
    acceptance=False,
    commander_scenario="single",
    no_capture=False,
    presentation="current",
    xmage_root=transport.DEFAULT_BUNDLE,
    jdk_path=transport.DEFAULT_JDK,
):
    """Blocking worker with one private manifest and one viewer bootstrap; no per-action Python."""
    if (
        commander_scenario
        not in (
            "single",
            "tax",
            "grave-decline",
            "hand-accept",
            "hand-decline",
            "exile-accept",
            "exile-decline",
            "library-accept",
            "library-decline",
        )
        or commander_scenario != "single"
        and (not acceptance or setup.format != "commander")
    ):
        raise LiveGameError("COMMANDER_SCENARIO_INVALID")
    if (
        payment_mode not in ("auto", "manual", "full-control")
        or type(acceptance) is not bool
        or type(no_capture) is not bool
        or presentation not in ("current", "table")
    ):
        raise LiveGameError("PAYMENT_MODE_INVALID")
    payload = project_launch(
        setup, documents, version, deck_owners, engine_bundle=xmage_root
    )
    manifest = json.loads(payload)
    human = next(s for s in manifest["seats"] if s["controller"] == "local_human")
    player = Path(player).resolve()
    if not player.is_file():
        raise LiveGameError("UNITY_GAME_BUILD_MISSING")
    launch = launch or LiveGameLaunch()
    launch.allocate()
    result = None
    from .engine_fork import manifest_digest

    pin = manifest_digest(xmage_root)

    def consume(first, events, peers, port, server_process, server):
        nonlocal result
        report(dict(phase="Validating selected decks"))

        def server_request(command):
            request = str(uuid.uuid4())
            command = dict(command, request_id=request)
            server_process.stdin.write(json.dumps(command) + "\n")
            server_process.stdin.flush()
            path = server / "manaforge-responses" / (request + ".json")
            deadline = time.monotonic() + 20
            while not path.is_file():
                if (
                    cancel.is_set()
                    or server_process.poll() is not None
                    or time.monotonic() >= deadline
                ):
                    raise LiveGameError("UNITY_GAME_VALIDATION_FAILED")
                time.sleep(0.02)
            if path.stat().st_size > 1024 * 1024:
                raise LiveGameError("UNITY_GAME_VALIDATION_FAILED")
            response = json.loads(path.read_text(encoding="utf-8"))
            path.unlink()
            return response

        from .rules_identity import canonical_cards

        names = canonical_cards(
            e.get("oracle_id")
            for seat in manifest["seats"]
            for e in seat["document"]["deck"]["entries"]
        )
        engine_manifest = resolve_rules_manifest(manifest, server_request, names)
        for seat in engine_manifest["seats"]:
            entries = seat["document"]["deck"]["entries"]
            cards = [
                dict(
                    name=e["name"],
                    set=e["set_code"].upper(),
                    number=e["collector_number"],
                    quantity=e["quantity"],
                )
                for e in entries
                if e["section"] == "mainboard"
                and e["entry_id"] not in seat["document"]["deck"]["commander_entry_ids"]
            ]
            sideboard = [
                dict(
                    name=e["name"],
                    set=e["set_code"].upper(),
                    number=e["collector_number"],
                    quantity=e["quantity"],
                )
                for e in entries
                if e["section"] in ("sideboard", "commander")
                or e["entry_id"] in seat["document"]["deck"]["commander_entry_ids"]
            ]
            if (
                server_request(
                    dict(
                        command="validate_deck",
                        format=setup.format,
                        cards=cards,
                        sideboard=sideboard,
                    )
                ).get("eligible")
                is not True
            ):
                raise LiveGameError("UNITY_GAME_DECK_INVALID")

        def cleanup_runtime():
            return (
                transport.stop_process(server_process, "shutdown").get("reaped") is True
            )

        owner = launch.owner = LaunchOwner(
            startup_timeout=120, runtime_cleanup=cleanup_runtime
        )
        key = bytearray(secrets.token_bytes(32))
        root = launch.root

        def wait_json(name, seconds=90):
            path = root / (name + ".json")
            deadline = time.monotonic() + seconds
            while not path.is_file():
                if cancel.is_set():
                    raise LiveGameError("LAUNCH_CANCELLED")
                if (root / "game-error.json").is_file():
                    error = json.loads(
                        (root / "game-error.json").read_text(encoding="utf-8")
                    )
                    code = error.get("code")
                    raise LiveGameError(
                        code
                        if isinstance(code, str)
                        and re.fullmatch(r"[A-Z_0-9]{1,100}", code)
                        else "UNITY_GAME_ENGINE_FAILED"
                    )
                owner.check_health()
                if time.monotonic() >= deadline:
                    raise LiveGameError("UNITY_GAME_STARTUP_TIMEOUT")
                time.sleep(0.02)
            if path.stat().st_size > 16384:
                raise LiveGameError("UNITY_GAME_READY_INVALID")
            return json.loads(path.read_text(encoding="utf-8"))

        try:
            report(dict(phase="Starting native Unity game"))
            owner.start_gateway(
                [
                    str(Path(xmage_root) / "java/jre1.8.0_201/bin/java.exe"),
                    "-Djava.awt.headless=true",
                    "-Dfile.encoding=UTF-8",
                    "-Djava.net.preferIPv4Stack=true",
                    "-Dmanaforge.adapterVersion=" + ADAPTER_VERSION,
                    "-Dmanaforge.commanderScenario=" + commander_scenario,
                    "-Dmanaforge.commanderAcceptance="
                    + str(acceptance and setup.format == "commander").lower(),
                    "-Dmanaforge.paymentMode=" + payment_mode.upper().replace("-", "_"),
                    "-cp",
                    str(server.parent / "classes") + os.pathsep + str(server / "lib/*"),
                    "ManaforgeLiveGame",
                    str(port),
                    pin,
                    str(root / "gateway-ready.json"),
                    str(root / "metadata-context.json"),
                ],
                cwd=str(root),
                launch_manifest=json.dumps(
                    engine_manifest,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ).encode("utf-8"),
                expect_manifest_validation=True,
            )
            owner.wait_gateway_manifest_validation(timeout=20)
            gateway = owner.gateway_process
            secret = json.dumps(
                dict(live_opening_bootstrap_version=1, viewer_key_hex=key.hex())
            ).encode()
            gateway.stdin.write(len(secret).to_bytes(4, "big") + secret)
            gateway.stdin.flush()
            provision_metadata(
                gateway, server_process, server, root / "metadata-context.json", pin
            )
            address = wait_json("gateway-ready")
            if (
                set(address) != {"host", "port"}
                or address["host"] != "127.0.0.1"
                or type(address["port"]) is not int
                or not 1 <= address["port"] <= 65535
            ):
                raise LiveGameError("UNITY_GAME_READY_INVALID")
            owner.gateway_ready()
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
            command += ["-manaforgePresentation", presentation]
            if no_capture:
                command += ["-manaforgeNoCapture", "1"]
            if acceptance:
                command += [
                    "-manaforgeGameAcceptance",
                    "1",
                    "-manaforgeCommanderScenario",
                    commander_scenario,
                ]
            artwork_directory, artwork_pin = prepare_local_artwork(
                human["document"], root, manifest["manifest_id"], human["seat_id"]
            )
            owner.start_client(
                command,
                cwd=str(player.parent),
                viewer_bootstrap=export_viewer_bootstrap(
                    port=address["port"],
                    session_id=manifest["manifest_id"],
                    viewer_id=human["seat_id"],
                    engine_version="1.4.62-V1",
                    artifact_manifest_sha256=pin,
                    viewer_key=key,
                    artwork_directory=artwork_directory,
                    artwork_manifest_sha256=artwork_pin,
                ),
            )
            ready = wait_json("game-ready")
            if ready != dict(live_game_version=1, authenticated=True):
                raise LiveGameError("UNITY_GAME_READY_INVALID")
            owner.client_ready()
            report(dict(phase="Unity game running"))
            deadline = time.monotonic() + 21600
            closing_at = None
            while owner.client_exit_code is None:
                if cancel.wait(0.05):
                    owner.request_cancel()
                    result = dict(outcome=None, cancelled=True)
                    return
                if time.monotonic() >= deadline:
                    raise LiveGameError("UNITY_GAME_SESSION_TIMEOUT")
                if owner.client_exit_code is not None:
                    break
                if (root / "game-closing.json").is_file():
                    closing_at = closing_at or time.monotonic()
                    if time.monotonic() - closing_at > 10:
                        raise LiveGameError("UNITY_GAME_PLAYER_EXIT_TIMEOUT")
                    continue
                owner.check_health()
            if owner.client_exit_code != 0:
                raise LiveGameError("UNITY_GAME_PLAYER_FAILED")
            closed = wait_json("game-closed", 1)
            focused_scenario = acceptance and commander_scenario not in (
                "single",
                "tax",
            )
            if focused_scenario:
                certificate = wait_json("game-scenario", 1)
                validate_scenario_close_report(closed, certificate, commander_scenario)
                closed.update(certificate)
            else:
                validate_close_report(closed)
            if closed.get("outcome") is not None:
                native = wait_json("game-result", 1)
                if native.get("outcome") != closed["outcome"] or native[
                    "outcome"
                ] not in ("win", "loss", "draw"):
                    raise LiveGameError("UNITY_GAME_RESULT_UNPROVEN")
            if acceptance and setup.format == "commander" and not focused_scenario:
                proof = wait_json("game-result", 1)
                if (
                    proof.get("native_commander_damage_lethal_verified") is not True
                    or proof.get("native_commander_roster_cast_verified") is not True
                ):
                    raise LiveGameError("UNITY_COMMANDER_ACCEPTANCE_UNPROVEN")
                closed.update(
                    {
                        key: proof[key]
                        for key in (
                            "native_commanders_cast",
                            "native_commander_damage_lethal_verified",
                            "native_commander_roster_cast_verified",
                        )
                    }
                )
                if commander_scenario == "tax":
                    if proof.get("native_commander_tax_verified") is not True:
                        raise LiveGameError("UNITY_COMMANDER_TAX_UNPROVEN")
                    closed["native_commander_tax_verified"] = True
            if acceptance and (
                (closed.get("outcome") is None and not focused_scenario)
                or closed.get("confirmed") != closed.get("snapshots", 0) - 1
            ):
                raise LiveGameError("UNITY_GAME_ACCEPTANCE_UNPROVEN")
            result = closed
        finally:
            key[:] = bytes(len(key))
            launch.close()

    try:
        report(dict(phase="Preparing pinned native engine"))
        proof = transport.run_proof(
            Path(xmage_root),
            Path(jdk_path),
            runtime_consumer=consume,
            cancel=cancel,
            payment_context_probe=True,
        )
        if not proof.get("success"):
            error = launch.last_error or proof.get("error")
            raise LiveGameError(
                error
                if isinstance(error, str) and re.fullmatch(r"[A-Z_0-9]{1,100}", error)
                else "UNITY_GAME_RUNTIME_FAILED"
            )
        return result
    finally:
        launch.close()


def prepare_local_artwork(document, root, session_id, viewer_id, service=None):
    """Reuse Core's offline cache for the viewer's own deck; never read AI entries.

    The surface still requires a current authenticated visible printing before binding.
    Missing metadata/images retain the existing unavailable-art presentation.
    """
    from .artwork_bundle import export_artwork_bundle

    ids = tuple(
        dict.fromkeys(
            entry["card_id"]
            for entry in document["deck"]["entries"]
            if entry.get("card_id")
        )
    )
    if not ids or len(ids) > 256:
        return None, None
    if service is None:
        try:
            from mtg_core.services import CardService
        except ImportError:
            return None, None

        def offline(*args, **kwargs):
            raise RuntimeError("LIVE_ARTWORK_NETWORK_FORBIDDEN")

        service = CardService(
            fetch_json_fn=offline, fetch_bytes_fn=offline, fetch_bulk_fn=offline
        )
    directory = Path(root) / "artwork"
    _, pin = export_artwork_bundle(
        service,
        ids,
        directory,
        session_id=session_id,
        viewer_id=viewer_id,
        max_edge=min(896, int((64 * 1024 * 1024 / (len(ids) * 4)) ** 0.5)),
        max_asset_bytes=64 * 1024 * 1024,
        allow_single_face=True,
    )
    return str(directory.resolve()), pin
