from __future__ import annotations

import argparse
import json
import os
import platform
import site
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

RESIDUE_DIRECTORY_NAMES = frozenset(
    {
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "venv",
    }
)
RESIDUE_FILE_NAMES = frozenset({".coverage", "coverage.xml"})
RESIDUE_SUFFIXES = frozenset({".pyc", ".pyo"})
COMMON_REQUIRED_ENV = (
    "PYTHONNOUSERSITE",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONUTF8",
    "PIP_CACHE_DIR",
)
PLATFORM_PATH_ENV = {
    "linux": ("HOME", "TMPDIR", "XDG_CACHE_HOME", "PIP_CACHE_DIR"),
    "windows": (
        "HOME",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
        "TEMP",
        "TMP",
        "PIP_CACHE_DIR",
    ),
}


def _resolved(path: str | Path, *, base: Path | None = None) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute() and base is not None:
        candidate = base / candidate
    return candidate.resolve(strict=False)


def path_is_within(path: str | Path, parent: str | Path) -> bool:
    candidate = _resolved(path)
    boundary = _resolved(parent)
    try:
        candidate.relative_to(boundary)
    except ValueError:
        return False
    return True


def collect_repo_residue(root: Path) -> list[str]:
    findings: list[str] = []
    for current, directories, files in os.walk(root):
        current_path = Path(current)
        if current_path == root:
            directories[:] = [name for name in directories if name != ".git"]
        retained: list[str] = []
        for name in directories:
            path = current_path / name
            if name in RESIDUE_DIRECTORY_NAMES:
                findings.append(path.relative_to(root).as_posix() + "/")
            else:
                retained.append(name)
        directories[:] = retained
        for name in files:
            path = current_path / name
            if name in RESIDUE_FILE_NAMES or path.suffix.lower() in RESIDUE_SUFFIXES:
                findings.append(path.relative_to(root).as_posix())
    return sorted(set(findings))


def git_output(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def environment_findings(
    *,
    root: Path,
    sandbox: Path,
    platform_label: str,
    environment: Mapping[str, str],
) -> list[str]:
    findings: list[str] = []
    label = platform_label.lower()
    required_path_vars = PLATFORM_PATH_ENV.get(label)
    if required_path_vars is None:
        return [f"UNSUPPORTED_PLATFORM_LABEL:{platform_label}"]

    for name in COMMON_REQUIRED_ENV:
        expected = "1" if name != "PIP_CACHE_DIR" else None
        value = environment.get(name, "")
        if not value:
            findings.append(f"ENV_MISSING:{name}")
        elif expected is not None and value != expected:
            findings.append(f"ENV_UNSAFE_VALUE:{name}={value}")

    for name in required_path_vars:
        value = environment.get(name, "")
        if not value:
            findings.append(f"ENV_PATH_MISSING:{name}")
            continue
        resolved = _resolved(value, base=root)
        if not path_is_within(resolved, sandbox):
            findings.append(f"ENV_PATH_OUTSIDE_SANDBOX:{name}={resolved}")

    python_path = environment.get("PYTHONPATH", "")
    if not python_path:
        findings.append("ENV_MISSING:PYTHONPATH")
    else:
        for entry in python_path.split(os.pathsep):
            if not entry:
                continue
            resolved = _resolved(entry, base=root)
            if not path_is_within(resolved, root):
                findings.append(f"PYTHONPATH_OUTSIDE_CHECKOUT:{resolved}")

    if site.ENABLE_USER_SITE:
        findings.append("PYTHON_USER_SITE_ENABLED")
    return findings


def sandbox_preexisting_files(sandbox: Path) -> list[str]:
    if not sandbox.exists():
        return ["SANDBOX_MISSING"]
    return sorted(
        path.relative_to(sandbox).as_posix()
        for path in sandbox.rglob("*")
        if path.is_file()
    )


def build_report(
    *,
    root: Path,
    sandbox: Path,
    expected_sha: str,
    platform_label: str,
    environment: Mapping[str, str],
) -> dict[str, object]:
    actual_sha = git_output(root, "rev-parse", "HEAD")
    git_status = git_output(root, "status", "--porcelain=v1", "--untracked-files=all")
    residue = collect_repo_residue(root)
    preexisting_files = sandbox_preexisting_files(sandbox)
    findings = environment_findings(
        root=root,
        sandbox=sandbox,
        platform_label=platform_label,
        environment=environment,
    )
    if actual_sha != expected_sha:
        findings.append(f"EXACT_HEAD_MISMATCH:{actual_sha}")
    if git_status:
        findings.append("CHECKOUT_NOT_CLEAN")
    if residue:
        findings.append("GENERATED_REPOSITORY_RESIDUE")
    if preexisting_files:
        findings.append("SANDBOX_PREEXISTING_FILES")

    return {
        "milestone": "M8",
        "title": "Clean Environment Reproduction",
        "status": "PASS" if not findings else "FAIL",
        "platform": platform_label.lower(),
        "expected_sha": expected_sha,
        "actual_sha": actual_sha,
        "checkout_clean": not bool(git_status),
        "repository_residue": residue,
        "sandbox_preexisting_files": preexisting_files,
        "python": {
            "executable": sys.executable,
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "user_site_enabled": bool(site.ENABLE_USER_SITE),
        },
        "findings": sorted(set(findings)),
        "release_state": "RELEASE_BLOCKED",
        "marketplace_write_enabled": False,
        "merge_to_main_authorized": False,
        "production_release_authorized": False,
    }


def write_report(report: Mapping[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def audit(arguments: argparse.Namespace) -> int:
    root = Path(arguments.root).resolve(strict=True)
    sandbox = Path(arguments.sandbox).resolve(strict=True)
    report = build_report(
        root=root,
        sandbox=sandbox,
        expected_sha=arguments.expected_sha,
        platform_label=arguments.platform_label,
        environment=os.environ,
    )
    write_report(report, Path(arguments.output))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Fail-closed clean-environment preflight for Quantum M8."
    )
    subparsers = result.add_subparsers(dest="command", required=True)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--root", required=True)
    audit_parser.add_argument("--sandbox", required=True)
    audit_parser.add_argument("--expected-sha", required=True)
    audit_parser.add_argument(
        "--platform-label", required=True, choices=sorted(PLATFORM_PATH_ENV)
    )
    audit_parser.add_argument("--output", required=True)
    audit_parser.set_defaults(handler=audit)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    return int(arguments.handler(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
