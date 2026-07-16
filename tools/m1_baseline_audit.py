#!/usr/bin/env python3
"""Temporary M0 recursive-tree exporter; then runs the parent audit tool."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = "tools/m1_baseline_audit.py"
PARENT_COPY = ROOT / "tools" / ".m0_parent_m1_baseline_audit.py"
EXPECTED_TARGET = "d5afcf5e4a28a5ce3cc144cf25db649aceda8b1f"


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def argument_value(name: str) -> str:
    try:
        return sys.argv[sys.argv.index(name) + 1]
    except (ValueError, IndexError) as exc:
        raise SystemExit(f"M0_TREE_EXPORT_MISSING_ARGUMENT:{name}") from exc


def export_parent_tree() -> None:
    instrumentation_head = git_bytes("rev-parse", "HEAD").decode("ascii").strip()
    target = git_bytes("rev-parse", "HEAD^").decode("ascii").strip()
    if target != EXPECTED_TARGET:
        raise SystemExit(
            f"M0_TREE_TARGET_MISMATCH:expected={EXPECTED_TARGET}:actual={target}"
        )

    parent_line = git_bytes("rev-list", "--parents", "-n", "1", "HEAD").decode("ascii").strip()
    parent_tokens = parent_line.split()
    if parent_tokens != [instrumentation_head, target]:
        raise SystemExit(f"M0_TREE_PARENT_RELATION_INVALID:{parent_line}")

    raw = git_bytes("ls-tree", "-r", "--full-tree", "--long", "-z", target)
    entries: list[dict[str, object]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, path_bytes = record.split(b"\t", 1)
        mode_b, type_b, sha_b, size_b = metadata.split(maxsplit=3)
        entries.append(
            {
                "mode": mode_b.decode("ascii"),
                "type": type_b.decode("ascii"),
                "object_sha": sha_b.decode("ascii"),
                "size_bytes": None if size_b == b"-" else int(size_b),
                "path": path_bytes.decode("utf-8", errors="surrogateescape"),
            }
        )

    paths = [str(item["path"]) for item in entries]
    canonical_entries = json.dumps(
        entries,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    platform_label = argument_value("--platform-label")
    output_dir = ROOT / "m1-artifacts" / platform_label
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0.0",
        "artifact_type": "M0_RECURSIVE_EXACT_HEAD_TREE",
        "target_exact_head": target,
        "instrumentation_head": instrumentation_head,
        "parent_relation": parent_tokens,
        "git_command": ["git", "ls-tree", "-r", "--full-tree", "--long", "-z", target],
        "entry_count": len(entries),
        "unique_path_count": len(set(paths)),
        "raw_ls_tree_sha256": hashlib.sha256(raw).hexdigest(),
        "canonical_entries_sha256": hashlib.sha256(canonical_entries).hexdigest(),
        "path_list_sha256": hashlib.sha256(("\n".join(paths) + "\n").encode("utf-8", errors="surrogateescape")).hexdigest(),
        "entries": entries,
    }
    target_path = output_dir / "m0-recursive-exact-head-tree.json"
    target_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        errors="surrogateescape",
    )


def run_parent_tool() -> int:
    target = git_bytes("rev-parse", "HEAD^").decode("ascii").strip()
    PARENT_COPY.write_bytes(git_bytes("show", f"{target}:{TOOL_PATH}"))
    try:
        completed = subprocess.run(
            [sys.executable, str(PARENT_COPY), *sys.argv[1:]],
            cwd=ROOT,
            check=False,
        )
        return completed.returncode
    finally:
        PARENT_COPY.unlink(missing_ok=True)


if __name__ == "__main__":
    export_parent_tree()
    raise SystemExit(run_parent_tool())
