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
)
_WRITE_ENABLE_PATTERN = re.compile(
    r"(?i)(?:marketplace[_-]?write(?:_enabled)?[\"']?|"
    r"MARKETPLACE_WRITE_ENABLED)\s*[:=]\s*"
    r"(?:\$?true|1|enabled|on)(?![A-Za-z0-9_])"
)
_SCANNED_SUFFIXES = {
    ".py", ".md", ".toml", ".sql", ".json", ".yaml", ".yml",
    ".ps1", ".cmd", ".bat", ".txt",
}

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
    scanner_path = Path(__file__).resolve()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", "__pycache__"} for part in path.parts):
            continue
        if path.suffix.lower() not in _SCANNED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        is_scanner = path.resolve() == scanner_path
        for marker in FORBIDDEN_SOURCE_MARKERS:
            if marker in text and not is_scanner:
                violations.append(f"{path.relative_to(root)}: {marker}")
        if not is_scanner and _WRITE_ENABLE_PATTERN.search(text):
            violations.append(
                f"{path.relative_to(root)}: marketplace write enablement"
            )
    if violations:
        raise RuntimeError("Forbidden source markers:\n" + "\n".join(violations))


def _diagnostic_group(path: str) -> str:
    top = path.split("/", 1)[0].upper()
    if top != "TESTS":
        return top
    filename = path.rsplit("/", 1)[-1]
    if filename.startswith("test_b1b_rescue"):
        return "TESTS_B1B_RESCUE"
    if filename.startswith("test_b1b"):
        return "TESTS_B1B"
    if filename.startswith("test_p16"):
        return "TESTS_P16"
    return "TESTS_OTHER"


def _diagnostic_group_order(group: str) -> tuple[int, str]:
    return (0 if group.startswith("TESTS_") else 1, group)


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
        groups.setdefault(_diagnostic_group(str(row[0])), []).append(row)
    print("UNITTEST_DIAGNOSTICS_BEGIN")
    for group in sorted(groups, key=_diagnostic_group_order):
        print(
            f"MANIFEST_REQUIRED_ENTRIES_{group}="
            + json.dumps(groups[group], separators=(",", ":"))
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
