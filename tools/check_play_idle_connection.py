"""Hosted regression: keep a real XMage client idle beyond its expiry interval."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Mtg_Projects"))
from mtg_play import connection_proof as transport  # noqa: E402 - repository script bootstrap
from mtg_play.diagnostics import LifecycleDiagnostics  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xmage-root", type=Path, required=True)
    parser.add_argument("--jdk-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = {}
    diagnostics = LifecycleDiagnostics()
    phase = "runtime_setup"
    reason = None

    def idle(bridge, events, launch_peer, port, server_process, server):
        nonlocal phase, reason
        phase = "idle_wait"
        # Server expiry is three minutes; no gameplay or status requests during idle.
        start = time.monotonic()
        while time.monotonic() - start < 240:
            if bridge.poll() is not None or server_process.poll() is not None:
                reason = "IDLE_ENGINE_PROCESS_EXITED"
                raise AssertionError("IDLE_ENGINE_PROCESS_EXITED")
            time.sleep(0.2)
        phase = "post_idle_status"
        transport.send(bridge, "status", "after-idle")
        status = events.wait("status", time.monotonic() + 20, "after-idle")
        if status.get("connected") is not True:
            reason = "IDLE_CONNECTION_EXPIRED"
            raise AssertionError("IDLE_CONNECTION_EXPIRED")
        phase = "server_expiry_check"
        log = (server.parent / "server.log").read_text(
            encoding="utf-8", errors="replace"
        )
        if "disconnected due connection problems" in log:
            reason = "IDLE_SERVER_EXPIRED_CLIENT"
            raise AssertionError("IDLE_SERVER_EXPIRED_CLIENT")
        evidence.update(idle_seconds=240, connected_after_idle=True)
        phase = "shutdown_or_cleanup"

    result = {}
    try:
        result = transport.run_proof(
            args.xmage_root,
            args.jdk_path,
            runtime_consumer=idle,
            diagnostics=diagnostics,
        )
    except Exception:
        # run_proof can reject installation before constructing its result.
        reason = "PROOF_EXCEPTION"
    evidence.update(sanitized_report(result, diagnostics, phase, reason))
    evidence["commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    if not evidence["success"]:
        print(json.dumps(evidence))
        raise AssertionError("IDLE_PROOF_FAILED")
    print(
        "Real XMage client remained connected after four minutes without gameplay input"
    )


def sanitized_report(result, diagnostics, phase, reason):
    """Allowlist evidence, never copy raw errors, workspace paths or transcripts."""
    success = result.get("success") is True
    failure = diagnostics.failure
    stage = failure["stage"] if failure else phase
    code = reason or (failure["code"] if failure else "IDLE_PROOF_FAILED")
    if not success and stage == "bridge_compilation":
        code = "BRIDGE_COMPILATION_FAILED"
    return {
        "success": success,
        "failed_stage": None if success else stage,
        "reason_code": None if success else code,
        "lifecycle": list(diagnostics.records),
    }


if __name__ == "__main__":
    main()
