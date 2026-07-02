from __future__ import annotations

import compileall
import json
import os
import re
import subprocess
import sys
from pathlib import Path


FORBIDDEN_SOURCE_MARKERS = (
    "ghp_",
    "github_pat_",
    "BEGIN PRIVATE KEY",
    "marketplace_write_enabled = true",
)

_FAILURE_HEADER = re.compile(r"^(?:FAIL|ERROR): .+$")
_FAILURE_DETAIL = re.compile(
    r"^(?:AssertionError|TypeError|ValueError|RuntimeError|ImportError|"
    r"ModuleNotFoundError|AttributeError|KeyError|FinanceError|"
    r"XlsxInspectionError|ReconciliationError):"
)
_SUMMARY_LINE = re.compile(r"^(?:Ran \d+ tests? in |FAILED \(|OK$)")


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def scan_forbidden_markers(root: Path) -> None:
    violations: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", "__pycache__"} for part in path.parts):
            continue
        if path.suffix.lower() not in {
            ".py",
            ".md",
            ".toml",
            ".sql",
            ".json",
            ".yaml",
            ".yml",
        }:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in FORBIDDEN_SOURCE_MARKERS:
            if marker in text and path.name != "ci.py":
                violations.append(f"{path.relative_to(root)}: {marker}")
    if violations:
        raise RuntimeError("Forbidden source markers:\n" + "\n".join(violations))


def _emit_manifest_diagnostics(lines: list[str]) -> None:
    required_entries: list[list[object]] = []
    extras: list[str] = []
    top_level: list[dict[str, object]] = []
    for line in lines:
        if line.startswith("MANIFEST_MISSING_ENTRY="):
            required_entries.append(json.loads(line.split("=", 1)[1]))
        elif line.startswith("MANIFEST_MISMATCH_TRACKED="):
            required_entries.append(json.loads(line.split("=", 1)[1]))
        elif line.startswith("MANIFEST_EXTRA_PATH="):
            extras.append(line.split("=", 1)[1])
        elif line.startswith("MANIFEST_TOP_LEVEL="):
            top_level.append(json.loads(line.split("=", 1)[1]))
    if not required_entries and not extras and not top_level:
        return
    required_entries.sort(key=lambda row: str(row[0]))
    groups: dict[str, list[list[object]]] = {}
    for row in required_entries:
        top = str(row[0]).split("/", 1)[0].upper()
        groups.setdefault(top, []).append(row)
    print("UNITTEST_DIAGNOSTICS_BEGIN")
    for top in sorted(groups):
        print(
            f"MANIFEST_REQUIRED_ENTRIES_{top}="
            + json.dumps(groups[top], separators=(",", ":"))
        )
    if extras:
        print("MANIFEST_EXTRA_PATHS=" + json.dumps(sorted(extras), separators=(",", ":")))
    if top_level:
        print("MANIFEST_TOP_LEVEL=" + json.dumps(top_level, separators=(",", ":")))
    print("UNITTEST_DIAGNOSTICS_END")


def _emit_test_output(result: subprocess.CompletedProcess[str]) -> None:
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode == 0:
        print(output, end="")
        return
    lines = output.splitlines()
    failure_index = [
        line
        for line in lines
        if _FAILURE_HEADER.match(line)
        or _FAILURE_DETAIL.match(line)
        or _SUMMARY_LINE.match(line)
    ]
    if failure_index:
        print("UNITTEST_FAILURE_INDEX_BEGIN")
        print("\n".join(failure_index))
        print("UNITTEST_FAILURE_INDEX_END")
    _emit_manifest_diagnostics(lines)
    print("UNITTEST_FAILURE_TAIL_BEGIN")
    print("\n".join(lines[-24:]))
    print("UNITTEST_FAILURE_TAIL_END")


def main() -> None:
    root = project_root()
    src = root / "src"

    if not compileall.compile_dir(src, quiet=1):
        raise SystemExit("compileall failed")

    scan_forbidden_markers(root)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(src)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(root / "tests"),
            "-t",
            str(root),
            "-p",
            "test_*.py",
            "-v",
        ],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    _emit_test_output(result)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
