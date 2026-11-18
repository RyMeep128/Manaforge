"""Fail closed unless exact source revisions have complete hosted release evidence."""
import argparse
import json
from pathlib import Path
import subprocess


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))


def require_workflow(repository, workflow, commit, *, broad=False):
    runs = api(f"repos/{repository}/actions/workflows/{workflow}/runs?head_sha={commit}&per_page=100")["workflow_runs"]
    for run in runs:
        if run["head_sha"] != commit or run["status"] != "completed" or run["conclusion"] != "success":
            continue
        jobs = api(f"repos/{repository}/actions/runs/{run['id']}/jobs?per_page=100")["jobs"]
        if not jobs or any(job.get("conclusion") != "success" for job in jobs):
            continue
        if broad:
            if not any(step["name"] == "Broad engine validation" and step.get("conclusion") == "success"
                       for job in jobs for step in job.get("steps", [])):
                continue
        print(f"Verified {workflow}: {run['html_url']}")
        return
    raise SystemExit(f"RELEASE_CHECK_UNAVAILABLE: {repository}/{workflow} at {commit}"
                     + (" with a successful broad engine step" if broad else ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    for name in ("play-protocol.yml", "play-payment-native.yml", "unity-play.yml", "play-live-opening.yml"):
        require_workflow(args.repository, name, args.commit)
    lock = json.loads((Path(__file__).resolve().parents[1] / "Mtg_Projects/mtg_play/engine-lock.json").read_text())
    require_workflow("RyMeep128/Manaforge-XMage", "manaforge-engine.yml", lock["fork_commit"], broad=True)
