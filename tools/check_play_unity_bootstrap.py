"""Headless packaged-player bootstrap proof, using public synthetic credentials only."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Mtg_Projects")]


def record(path, code):
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if value != dict(probe_version=1, fixture_only=True, code=code):
        raise RuntimeError("BOOTSTRAP_PROBE_REPORT_INVALID")


def wait_report(owner, path, code):
    from mtg_play.launch_lifecycle import LaunchLifecycleError

    deadline = time.monotonic() + 60
    while not path.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("BOOTSTRAP_PROBE_REPORT_TIMEOUT")
        try:
            owner.check_health()
        except LaunchLifecycleError:
            if not path.exists():
                raise RuntimeError("BOOTSTRAP_PROBE_CHILD_EXITED") from None
        time.sleep(0.01)
    record(path, code)


def run_case(player, root, name, payload, expected):
    from mtg_play.launch_lifecycle import LaunchOwner, LaunchState

    output = root / name
    output.mkdir()
    # The gateway is a dummy Python child with no descendants, not XMage.
    owner = LaunchOwner(startup_timeout=90, runtime_cleanup=lambda: True)
    try:
        owner.start_gateway(
            [sys.executable, "-I", "-c", "import sys; sys.stdin.buffer.read()"]
        )
        owner.gateway_ready()  # Test fixture lifecycle event, no peer-auth claim.
        owner.start_client(
            [
                str(player),
                "-batchmode",
                "-nographics",
                "-logFile",
                str(output / "player.log"),
                "-manaforgeBootstrapDiagnostic",
                str(output),
            ],
            viewer_bootstrap=payload,
        )
        if expected == "OWNER_EOF":
            wait_report(owner, output / "received.json", "BOOTSTRAP_RECEIVED")
            if owner.state != LaunchState.STARTING_CLIENT:
                raise RuntimeError("BOOTSTRAP_PROBE_PREMATURE_READINESS")
        else:
            wait_report(owner, output / "failed.json", expected)
        report = owner.close()
        if not report.confirmed or report.forced:
            raise RuntimeError("BOOTSTRAP_PROBE_ROOT_CLEANUP_FAILED")
        result = {item.role: item.exit_code for item in report.children}
        if result != dict(gateway=0, client=0 if expected == "OWNER_EOF" else 1):
            raise RuntimeError("BOOTSTRAP_PROBE_EXIT_INVALID")
        if expected == "OWNER_EOF":
            record(output / "closed.json", "OWNER_EOF")
        log = (output / "player.log").read_text(encoding="utf-8-sig", errors="replace")
        if bytes(range(32)).hex() in log or "viewer_key_hex" in log:
            raise RuntimeError("BOOTSTRAP_PROBE_PRIVATE_LOG")
        return dict(name=name, code=expected, root_exit_codes=result, forced=False)
    finally:
        if not owner.close().confirmed:
            raise RuntimeError("BOOTSTRAP_PROBE_CLEANUP_UNCONFIRMED")


def main():
    from mtg_play.viewer_bootstrap import export_viewer_bootstrap

    parser = argparse.ArgumentParser(description=__doc__)
    project = ROOT / "Mtg_Projects/mtg_play_unity"
    parser.add_argument(
        "--player", type=Path, default=project / "Builds/Windows/ManaforgePlay.exe"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project / "Artifacts" / ("BootstrapPlayer-" + uuid.uuid4().hex[:12]),
    )
    args = parser.parse_args()
    output, allowed = args.output.resolve(), (project / "Artifacts").resolve()
    if output == allowed or not output.is_relative_to(allowed) or output.exists():
        parser.error("Choose a new directory under Unity Artifacts")
    player = args.player.resolve()
    if not player.is_file():
        parser.error("Build the Unity Windows player first")
    output.mkdir(parents=True)
    values = dict(
        port=43210,
        session_id="fixture-session",
        viewer_id="seat-one",
        engine_version="fixture-engine",
        artifact_manifest_sha256="a" * 64,
        viewer_key=bytes(range(32)),
    )
    cases = [
        run_case(
            player, output, "owner-eof", export_viewer_bootstrap(**values), "OWNER_EOF"
        )
    ]
    cases.append(run_case(player, output, "malformed", b"{", "BOOTSTRAP_PIPE_PAYLOAD"))
    cases.append(run_case(player, output, "no-frame", None, "BOOTSTRAP_PIPE_TIMEOUT"))
    values["viewer_id"] = "different-seat"
    cases.append(
        run_case(
            player,
            output,
            "non-fixture",
            export_viewer_bootstrap(**values),
            "BOOTSTRAP_DIAGNOSTIC_CONTEXT",
        )
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    report = dict(
        report_version=1,
        fixture_only=True,
        passed=True,
        player_sha256=hashlib.sha256(player.read_bytes()).hexdigest(),
        runtime_assembly_sha256=hashlib.sha256(
            (
                player.parent / (player.stem + "_Data") / "Managed/Manaforge.Play.dll"
            ).read_bytes()
        ).hexdigest(),
        source_commit=commit,
        source_dirty=dirty,
        cases=cases,
        descendant_containment_proven=False,
    )
    (output / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "Packaged Unity bootstrap: 4 cases passed; roots exited without forced termination"
    )
    print(f"Sanitized report: {output / 'report.json'}")


if __name__ == "__main__":
    main()
