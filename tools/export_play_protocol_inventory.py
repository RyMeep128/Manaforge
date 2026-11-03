"""Inventory current Python contracts without importing Qt, Core or XMage.

This is source inventory, not the future cross-language wire schema.
Run with --check in CI to detect drift; omit it to regenerate the artifact.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAY = ROOT / "Mtg_Projects" / "mtg_play"
OUTPUT = PLAY / "protocol" / "python-api-inventory.json"


def inventory():
    source = (PLAY / "contracts.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    records = {}
    methods = {}
    versions = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith("VERSION"):
                    versions[target.id] = ast.literal_eval(node.value)
        if not isinstance(node, ast.ClassDef):
            continue
        fields = []
        for member in node.body:
            if isinstance(member, ast.AnnAssign):
                field = {
                    "name": member.target.id,
                    "python_type": ast.unparse(member.annotation),
                    "required": member.value is None,
                }
                if member.value is not None:
                    field["python_default"] = ast.unparse(member.value)
                fields.append(field)
            if node.name == "GameSession" and isinstance(member, ast.FunctionDef):
                methods[member.name] = ast.unparse(member).split(":\n", 1)[0]
        if any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id == "dataclass"
            for decorator in node.decorator_list
        ):
            records[node.name] = fields

    manifest = PLAY / "artifacts.json"
    engine = json.loads(manifest.read_text(encoding="utf-8"))
    # Candidate strings deliberately retain provenance: not all uppercase literals
    # are public errors, and dynamically constructed codes need manual review.
    candidates = {}
    for filename in ("adapter.py", "decks.py", "connection_proof.py"):
        path = PLAY / filename
        literals = {
            node.value
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.isupper()
            and "_" in node.value
            and all(character.isupper() or character == "_" for character in node.value)
        }
        candidates[filename] = sorted(literals)
    return {
        "inventory_format": 1,
        "purpose": "Existing Python source inventory; not a wire schema or parity claim",
        "versions": versions,
        "engine_version": engine["engine"],
        "engine_upstream_tag": engine["upstream_tag"],
        "artifact_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "records": records,
        "session_methods": methods,
        "uppercase_code_candidates_by_source": candidates,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = json.dumps(inventory(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != expected:
            parser.exit(
                1, "Play inventory drift: regenerate and review the protocol impact.\n"
            )
        print("Play Python API inventory matches current source.")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(expected, encoding="utf-8")
        print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
