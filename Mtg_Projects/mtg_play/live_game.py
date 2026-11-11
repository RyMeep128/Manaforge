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
from .session_logs import retain_session_logs
from .viewer_bootstrap import export_viewer_bootstrap


SHARED_ORGANIZATION_ENABLED = (
    False  # Activate only after exact-SHA Unity and full-game acceptance.
)


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
        setup.format not in ("freeform", "commander", "unrestricted_commander")
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
        self.log_directory = None
        self.payment_diagnostics = None
        self.unsupported_diagnostics = None
        self.process_diagnostics = None
        self.engine_identity = None
        self.version = None
        self.player = None

    def allocate(self):
        self.root = Path(tempfile.mkdtemp(prefix="manaforge-live-game-"))
        self._parent = self.root.parent.resolve()
        stat = self.root.stat()
        self._identity = (stat.st_dev, stat.st_ino)

    def close(self):
        if self.owner is not None:
            cleanup = self.owner.close()
            self.process_diagnostics = [
                dict(
                    role=child.role,
                    exit_code=child.exit_code,
                    forced=child.forced,
                    reaped=child.reaped,
                )
                for child in getattr(cleanup, "children", ())
                if child.role in ("gateway", "client")
            ]
            if not cleanup.confirmed:
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
                    if not error.is_file():
                        # Successful normal games also carry engine payment diagnostics.
                        error = resolved / "game-result.json"
                    if (
                        error.is_file()
                        and not error.is_symlink()
                        and error.stat().st_size <= 8192
                    ):
                        error_report = json.loads(error.read_text(encoding="utf-8"))
                        code = error_report.get("code")
                        self.payment_diagnostics = {
                            key: value
                            for key, value in error_report.items()
                            if key
                            in {
                                "native_auto_payment_last_reason",
                                "native_auto_payment_steps",
                                "native_auto_payment_completed",
                                "native_auto_payment_manual_windows",
                                "native_auto_payment_mode",
                            }
                            and (
                                type(value) is int
                                and 0 <= value <= 1000000
                                or isinstance(value, str)
                                and re.fullmatch(r"[A-Z_]{1,100}", value)
                            )
                        } or None
                        outcomes = error_report.get("native_auto_payment_outcomes")
                        if isinstance(outcomes, dict) and len(outcomes) <= 32:
                            safe_outcomes = {
                                key: count
                                for key, count in outcomes.items()
                                if isinstance(key, str)
                                and re.fullmatch(r"[A-Z_]{1,100}", key)
                                and type(count) is int
                                and 0 <= count <= 1000000
                            }
                            if safe_outcomes:
                                self.payment_diagnostics = (
                                    self.payment_diagnostics or {}
                                )
                                self.payment_diagnostics[
                                    "native_auto_payment_outcomes"
                                ] = safe_outcomes
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
                try:
                    unsupported = resolved / "game-unsupported.json"
                    if (
                        unsupported.is_file()
                        and not unsupported.is_symlink()
                        and unsupported.stat().st_size <= 2048
                    ):
                        value = json.loads(unsupported.read_text(encoding="utf-8"))
                        self.unsupported_diagnostics = {
                            key: item
                            for key, item in value.items()
                            if key in ("code", "prompt_family", "phase", "step")
                            and isinstance(item, str)
                            and re.fullmatch(r"[A-Z_0-9]{1,100}", item)
                            or key
                            in (
                                "targets_count",
                                "choices_count",
                                "cards_count",
                                "amounts_count",
                            )
                            and type(item) is int
                            and 0 <= item <= 256
                        } or None
                except (OSError, ValueError, AttributeError):
                    pass
                try:
                    self.log_directory = retain_session_logs(
                        resolved,
                        summary=self.summary,
                        error=self.last_error,
                        client_errors=self.client_errors,
                        version=self.version,
                        player=self.player,
                        payment=self.payment_diagnostics,
                        unsupported=self.unsupported_diagnostics,
                        processes=self.process_diagnostics,
                        engine=self.engine_identity,
                    )
                    if self.log_directory is not None and (
                        self.last_error or self.client_errors or self.summary is None
                    ):
                        from mtg_core.diagnostics import get_logger

                        get_logger(__name__).warning(
                            "Unity session logs retained directory=%s code=%s",
                            self.log_directory,
                            self.last_error or "NO_CONFIRMED_RESULT",
                        )
                except (OSError, ValueError):
                    # Diagnostic storage must not leave child processes or private
                    # manifests behind, nor replace the original game error.
                    from mtg_core.diagnostics import get_logger

                    get_logger(__name__).warning("UNITY_LOG_RETENTION_FAILED")
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
    concede_acceptance=False,
    require_auto_payment=False,
    commander_scenario="single",
    no_capture=False,
    rules_text_proof=None,
    artwork_proof=None,
    presentation="current",
    organization=False,
    xmage_root=transport.DEFAULT_BUNDLE,
    jdk_path=transport.DEFAULT_JDK,
):
    """Blocking worker with one private manifest and one viewer bootstrap; no per-action Python."""
    if type(organization) is not bool:
        raise LiveGameError("UNITY_GAME_ORGANIZATION_INVALID")
    organization_enabled = organization or SHARED_ORGANIZATION_ENABLED
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
    if (
        type(concede_acceptance) is not bool
        or concede_acceptance
        and (not acceptance or setup.format != "freeform" or require_auto_payment)
    ):
        raise LiveGameError("CONCEDE_ACCEPTANCE_INVALID")
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
    launch.version = version
    launch.player = player
    result = None
    from .engine_fork import installation_manifest, manifest_digest

    pin = manifest_digest(xmage_root)
    engine_pin = json.loads(
        installation_manifest(xmage_root).read_text(encoding="utf-8")
    )
    launch.engine_identity = {"manifest_sha256": pin}
    source_sha = engine_pin.get("fork_commit")
    if isinstance(source_sha, str) and re.fullmatch(r"[0-9a-f]{40}", source_sha):
        launch.engine_identity["source_sha"] = source_sha
    bundle_id = engine_pin.get("bundle_id")
    if isinstance(bundle_id, str) and re.fullmatch(
        r"[0-9a-f]{40}(?:-[0-9a-f]{12})?", bundle_id
    ):
        launch.engine_identity["bundle_id"] = bundle_id

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
                if (
                    e["section"] == "commander"
                    or (
                        e["section"] == "sideboard"
                        and setup.format != "unrestricted_commander"
                    )
                )
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

        public_artwork = None
        try:
            from .public_artwork import PublicArtworkServer

            public_artwork = PublicArtworkServer(
                root, manifest["manifest_id"], human["seat_id"]
            )
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
                    "-Dmanaforge.publicArtwork=" + str(root / "artwork/manifest.json"),
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
                dict(
                    live_opening_bootstrap_version=1,
                    viewer_key_hex=key.hex(),
                    **({"organization_version": 2} if organization_enabled else {}),
                )
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
            if rules_text_proof is not None:
                command += ["-manaforgeRulesTextProof", "1"]
            if artwork_proof is not None:
                command += [
                    "-manaforgeArtworkProof",
                    "1",
                    "-manaforgeGameAcceptance",
                    "1",
                ]
            if concede_acceptance:
                command += ["-manaforgeConcedeAcceptance", "1"]
            if no_capture:
                command += ["-manaforgeNoCapture", "1"]
            if require_auto_payment:
                command += ["-manaforgeRequireAutoPayment", "1"]
            if acceptance:
                command += [
                    "-manaforgeGameAcceptance",
                    "1",
                    "-manaforgeCommanderScenario",
                    commander_scenario,
                ]
            artwork_directory, artwork_pin = (
                public_artwork.directory,
                public_artwork.pin,
            )
            owner.start_client(
                command,
                cwd=str(player.parent),
                viewer_bootstrap=export_viewer_bootstrap(
                    format=manifest["format"],
                    organization_version=2 if organization_enabled else None,
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
            if artwork_proof is not None:
                certificate = wait_json("artwork-proof", 1)
                if not all(
                    certificate.get(key) is True
                    for key in ("mountain", "opponent", "token")
                ):
                    raise LiveGameError("UNITY_ARTWORK_UNPROVEN")
                destination = Path(artwork_proof)
                destination.mkdir(parents=True, exist_ok=False)
                for name in (
                    "artwork-proof.json",
                    "artwork-mountain.png",
                    "artwork-opponent.png",
                    "artwork-token.png",
                ):
                    shutil.copyfile(root / name, destination / name)
            if rules_text_proof is not None:
                certificate = wait_json("rules-text-proof", 1)
                if (
                    not (certificate.get("displayed_rules") or "").strip()
                    or certificate.get("visible") is not True
                ):
                    raise LiveGameError("UNITY_RULES_TEXT_UNPROVEN")
                destination = Path(rules_text_proof)
                destination.mkdir(parents=True, exist_ok=False)
                for name in ("rules-text-proof.json", "rules-text-proof.png"):
                    shutil.copyfile(root / name, destination / name)
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
                if require_auto_payment:
                    if (
                        native.get("native_auto_payment_mode") != "AUTO"
                        or type(native.get("native_auto_payment_steps")) is not int
                        or native["native_auto_payment_steps"] < 1
                        or type(native.get("native_auto_payment_completed")) is not int
                        or native["native_auto_payment_completed"] < 1
                        or native.get("native_auto_payment_manual_windows") != 0
                    ):
                        raise LiveGameError("UNITY_GAME_AUTO_PAYMENT_UNPROVEN")
                    closed.update(
                        {
                            key: value
                            for key, value in native.items()
                            if key.startswith("native_auto_payment_")
                        }
                    )
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
            if (
                acceptance
                and not concede_acceptance
                and presentation == "current"
                and setup.format == "freeform"
            ):
                layout = closed.get("hud_layout")
                if not isinstance(layout, dict) or not all(
                    layout.get(key) is True
                    for key in (
                        "complete",
                        "opened",
                        "moved",
                        "resized",
                        "input_gate",
                        "cancel",
                        "reset",
                        "custom_gameplay",
                    )
                ):
                    raise LiveGameError("UNITY_GAME_ACCEPTANCE_UNPROVEN")
            if concede_acceptance and (
                closed.get("outcome") != "loss"
                or closed.get("concession_menu_submitted") is not True
                or closed.get("confirmed") != 1
            ):
                raise LiveGameError("UNITY_CONCESSION_UNPROVEN")
            result = closed
        finally:
            key[:] = bytes(len(key))
            if rules_text_proof is not None or artwork_proof is not None:
                destination = Path(rules_text_proof or artwork_proof)
                destination.mkdir(parents=True, exist_ok=True)
                for name in (
                    "player.log",
                    "mageserver.log",
                    "game-error.json",
                    "game-unsupported.json",
                    "game-closed.json",
                    "artwork-progress.json",
                    "artwork-progress.png",
                    "artwork-mountain.png",
                    "artwork-opponent.png",
                    "artwork-token.png",
                ):
                    if (root / name).is_file():
                        shutil.copyfile(root / name, destination / name)
            try:
                launch.close()
            finally:
                if public_artwork is not None:
                    public_artwork.close()

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
