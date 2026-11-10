"""Hosted regression: keep a real XMage client idle beyond its expiry interval."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Mtg_Projects"))
from mtg_play import connection_proof as transport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xmage-root", type=Path, required=True)
    parser.add_argument("--jdk-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = {}

    def idle(bridge, events, launch_peer, port, server_process, server):
        # Server expiry is three minutes; no gameplay or status requests during idle.
        start = time.monotonic()
        while time.monotonic() - start < 240:
            if bridge.poll() is not None or server_process.poll() is not None:
                raise AssertionError("IDLE_ENGINE_PROCESS_EXITED")
            time.sleep(.2)
        transport.send(bridge, "status", "after-idle")
        status = events.wait("status", time.monotonic() + 20, "after-idle")
        if status.get("connected") is not True:
            raise AssertionError("IDLE_CONNECTION_EXPIRED")
        log = (server.parent / "server.log").read_text(encoding="utf-8", errors="replace")
        if "disconnected due connection problems" in log:
            raise AssertionError("IDLE_SERVER_EXPIRED_CLIENT")
        evidence.update(idle_seconds=240, connected_after_idle=True)

    result = transport.run_proof(args.xmage_root, args.jdk_path, runtime_consumer=idle)
    if not result.get("success"):
        raise AssertionError("IDLE_PROOF_FAILED")
    evidence["commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("Real XMage client remained connected after four minutes without gameplay input")


if __name__ == "__main__":
    main()
