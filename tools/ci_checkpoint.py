"""Persistent, non-polling CI checkpoint evidence. Never merges or runs tests."""

import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess


def command(*args):
    return subprocess.check_output(args, text=True, encoding="utf-8").strip()


def git(*args):
    return command("git", *args)


def ancestor(base, head):
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, head], check=False
    ).returncode == 0


def api(path):
    # --slurp retains page boundaries, then flatten all pages explicitly.
    pages = json.loads(command("gh", "api", "--paginate", "--slurp", path))
    return pages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "checkpoint", "record-promotion"])
    parser.add_argument("--replace-failed", action="store_true")
    parser.add_argument("--evidence")
    parser.add_argument("--baseline-accepted", action="store_true")
    args = parser.parse_args()
    root = Path(git("rev-parse", "--show-toplevel"))
    os.chdir(root)
    common = Path(git("rev-parse", "--git-common-dir")).resolve()
    path = common / "manaforge-ci-checkpoint.json"
    head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "schema": 1, "branch": "codex/play-live-first-land", "anchor": head,
        "baseline_accepted": False, "pending": None, "history": [],
    }
    if branch != state["branch"]:
        parser.error(f"Use active branch {state['branch']}; found {branch!r}")
    if not ancestor(state["anchor"], head):
        parser.error("Cadence anchor is not an ancestor of HEAD; investigate history")
    count = int(git("rev-list", "--count", "--first-parent", f"{state['anchor']}..{head}"))
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if args.action == "checkpoint":
        if args.replace_failed:
            pending = state["pending"]
            if not pending or pending["sha"] == head:
                parser.error("Replacement requires a pending candidate and a new commit")
            if not ancestor(pending["sha"], head):
                parser.error("Correction must descend from pending candidate")
            state["history"].append({"superseded": pending, "at": now})
            state["pending"] = None
        if state["pending"] is None and (
            args.replace_failed or not state["baseline_accepted"] or count >= 3
        ):
            state["pending"] = {"sha": head, "created": now, "runs": []}
        if state["pending"]:
            pending = state["pending"]
            try:
                repo = json.loads(command("gh", "repo", "view", "--json", "nameWithOwner"))["nameWithOwner"]
                runs = [run for page in api(
                    f"repos/{repo}/actions/runs?head_sha={pending['sha']}&per_page=100"
                ) for run in page["workflow_runs"] if run["head_sha"] == pending["sha"]]
                snapshots = []
                for run in runs:
                    jobs = [job for page in api(
                        f"repos/{repo}/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs?per_page=100"
                    ) for job in page["jobs"]]
                    snapshots.append({key: run.get(key) for key in (
                        "id", "run_attempt", "path", "event", "head_sha", "status",
                        "conclusion", "html_url"
                    )} | {"jobs": jobs})
                pending.update(runs=snapshots, inspected=now, decision="review-required")
                pending.pop("blocker", None)
            except (OSError, subprocess.CalledProcessError, ValueError, KeyError) as exc:
                pending.update(inspected=now, decision="blocked", blocker=str(exc))
    elif args.action == "record-promotion":
        pending = state["pending"]
        if not pending or not args.evidence:
            parser.error("Pending candidate and --evidence are required")
        if not state["baseline_accepted"] and not args.baseline_accepted:
            parser.error("First baseline requires explicit --baseline-accepted evidence")
        if pending.get("decision") != "review-required" or not pending.get("runs"):
            parser.error("Capture Actions evidence before recording promotion")
        git("fetch", "origin", "main")
        if not ancestor(pending["sha"], "origin/main"):
            parser.error("Remote main does not contain pending candidate")
        if not ancestor(pending["sha"], head):
            parser.error("Development HEAD does not descend from pending candidate")
        state["history"].append({"promotion": pending, "main": git("rev-parse", "origin/main"),
                                 "evidence": args.evidence, "at": now})
        state.update(pending=None, anchor=head, baseline_accepted=True)
    if args.action != "status" or not path.exists():
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    print(json.dumps({"record": str(path), "commits_since_resolution": count,
                      "checkpoint_due": not state["baseline_accepted"] or count >= 3,
                      **state}, indent=2))


if __name__ == "__main__":
    main()
