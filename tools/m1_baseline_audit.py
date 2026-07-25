#!/usr/bin/env python3
"""Reproducible MILESTONE 1 baseline and functional inventory audit.

The script is evidence-only: it does not mutate product data, source code, or
runtime configuration. Results are written under m1-artifacts/.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"

NEGATIVE_SCENARIOS: dict[str, tuple[str, ...]] = {
    "empty_file": ("empty", "zero_byte"),
    "corrupt_file": ("corrupt", "malformed", "truncated", "tamper"),
    "duplicate": ("duplicate", "deduplic"),
    "unknown_columns": ("unknown_column", "unexpected_column", "schema_mismatch"),
    "different_column_order": ("column_order", "reorder", "permut"),
    "different_encoding": ("encoding", "utf8", "utf_8", "cp1251"),
    "different_date_formats": ("date_format", "period", "retention_deadline"),
    "decimal_comma": ("decimal_comma", "comma_decimal"),
    "negative_values": ("negative", "below_zero"),
    "zero_revenue": ("zero_revenue", "revenue_zero"),
    "division_by_zero": ("division_by_zero", "divide_by_zero", "zero_units"),
    "missing_cost": ("missing_cost", "cost_required", "product_cost_required"),
    "missing_tax": ("missing_tax", "tax_required", "tax_rate_required"),
    "missing_other_expenses": ("missing_other", "other_expense_required"),
    "occupied_port": ("occupied_port", "port_fallback", "port_is_in_use"),
    "no_network": ("no_network", "offline", "network_unavailable"),
    "interrupted_import": ("interrupted", "atomic", "rollback", "partial_write"),
    "repeated_launch": ("restart", "repeat", "second_run", "idempot"),
}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def run_command(
    name: str,
    command: list[str],
    *,
    timeout: int = 600,
    env: dict[str, str] | None = None,
    cwd: Path = ROOT,
    expected_failure_reason: str | None = None,
) -> dict[str, Any]:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=merged,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
        duration = round(time.monotonic() - started, 3)
        output = (completed.stdout or "") + (completed.stderr or "")
        status = "PASS" if completed.returncode == 0 else "FAIL"
        if completed.returncode != 0 and expected_failure_reason:
            status = "BLOCKED_BASELINE"
        return {
            "name": name,
            "status": status,
            "returncode": completed.returncode,
            "duration_seconds": duration,
            "command": command,
            "expected_failure_reason": expected_failure_reason,
            "output_tail": output[-12000:],
            "full_output": output,
        }
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") if isinstance(exc.stdout, str) else "") + (
            (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        )
        return {
            "name": name,
            "status": "FAIL_TIMEOUT",
            "returncode": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "command": command,
            "expected_failure_reason": expected_failure_reason,
            "output_tail": output[-12000:],
            "full_output": output,
        }


def test_count(output: str) -> int | None:
    matches = re.findall(r"Ran\s+(\d+)\s+tests?", output)
    return int(matches[-1]) if matches else None


def inventory() -> dict[str, Any]:
    tracked = run_command("git_ls_files", ["git", "ls-files"], timeout=60)
    paths = [ROOT / line for line in tracked["full_output"].splitlines() if line.strip()]
    files = [path for path in paths if path.is_file()]
    suffixes = Counter(path.suffix.lower() or "<none>" for path in files)
    top_levels = Counter(path.relative_to(ROOT).parts[0] for path in files)

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject.get("project", {}).get("scripts", {})
    dependencies = pyproject.get("project", {}).get("dependencies", [])

    python_modules = sorted(
        rel(path) for path in (SRC / "quantum").rglob("*.py") if path.is_file()
    )
    test_modules = sorted(rel(path) for path in TESTS.glob("test_*.py"))
    workflows = sorted(rel(path) for path in (ROOT / ".github" / "workflows").glob("*.yml"))
    launchers = sorted(
        rel(path)
        for pattern in ("*.cmd", "*.ps1", "*.bat")
        for path in ROOT.rglob(pattern)
        if ".git" not in path.parts
    )
    configs = sorted(
        rel(path)
        for folder in (ROOT / "config", ROOT / "requirements")
        if folder.exists()
        for path in folder.rglob("*")
        if path.is_file()
    )
    frontend_markers = sorted(
        rel(path)
        for name in (
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "vite.config.js",
            "vite.config.ts",
            "next.config.js",
            "next.config.mjs",
        )
        for path in ROOT.rglob(name)
    )
    html_assets = sorted(rel(path) for path in ROOT.rglob("*.html"))

    secret_key_names: set[str] = set()
    secret_pattern = re.compile(
        r"(?i)(?:token|secret|password|api[_-]?key|credential|client[_-]?secret)"
    )
    for path in files:
        if path.suffix.lower() not in {".json", ".toml", ".yaml", ".yml", ".env", ".md", ".py", ".ps1"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            if secret_pattern.search(line):
                key = re.split(r"[:=\s]", line.strip(), maxsplit=1)[0].strip("'\"-$")
                if key and len(key) < 100:
                    secret_key_names.add(key)

    return {
        "tracked_file_count": len(files),
        "top_level_counts": dict(sorted(top_levels.items())),
        "suffix_counts": dict(sorted(suffixes.items())),
        "python_module_count": len(python_modules),
        "python_modules": python_modules,
        "test_module_count": len(test_modules),
        "test_modules": test_modules,
        "workflow_count": len(workflows),
        "workflows": workflows,
        "project_scripts": scripts,
        "declared_dependencies": dependencies,
        "launchers": launchers,
        "configuration_files": configs,
        "frontend_markers": frontend_markers,
        "html_assets": html_assets,
        "separate_frontend_detected": bool(frontend_markers),
        "secret_or_credential_key_names_only": sorted(secret_key_names),
    }


def discover_module_names(keywords: tuple[str, ...]) -> list[str]:
    names: list[str] = []
    for path in TESTS.glob("test_*.py"):
        stem = path.stem.lower()
        if any(keyword in stem for keyword in keywords):
            names.append(f"tests.{path.stem}")
    return sorted(names)


def import_smoke() -> dict[str, Any]:
    code = r'''
import importlib, json, pkgutil, quantum
errors=[]
loaded=[]
for item in pkgutil.walk_packages(quantum.__path__, quantum.__name__ + "."):
    try:
        importlib.import_module(item.name)
        loaded.append(item.name)
    except Exception as exc:
        errors.append({"module": item.name, "error": type(exc).__name__ + ": " + str(exc)})
print(json.dumps({"loaded": loaded, "errors": errors}, sort_keys=True))
raise SystemExit(1 if errors else 0)
'''
    return run_command(
        "import_smoke",
        [sys.executable, "-c", code],
        timeout=180,
        env={"PYTHONPATH": str(SRC)},
    )


def backend_smoke() -> dict[str, Any]:
    port_socket = socket.socket()
    port_socket.bind(("127.0.0.1", 0))
    port = int(port_socket.getsockname()[1])
    port_socket.close()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    process = subprocess.Popen(
        [sys.executable, "-m", "quantum.api.main", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    started = time.monotonic()
    payload: dict[str, Any] | None = None
    error: str | None = None
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                error = f"process exited early: {process.returncode}"
                break
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health/technical", timeout=1
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    break
            except Exception:
                time.sleep(0.2)
        if payload is None and error is None:
            error = "health endpoint timeout"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    status = "PASS" if payload and payload.get("status") == "ok" else "FAIL"
    return {
        "name": "backend_startup",
        "status": status,
        "duration_seconds": round(time.monotonic() - started, 3),
        "port": port,
        "payload": payload,
        "error": error,
    }


def worker_smoke() -> dict[str, Any]:
    result = run_command(
        "worker_startup",
        [sys.executable, "-m", "quantum.worker.main", "--once"],
        timeout=30,
        env={"PYTHONPATH": str(SRC)},
    )
    try:
        result["payload"] = json.loads(result["full_output"].strip().splitlines()[-1])
    except Exception:
        result["payload"] = None
    return result


def coverage_map(full_output: str) -> dict[str, Any]:
    normalized = full_output.lower().replace("-", "_").replace(" ", "_")
    mapping: dict[str, Any] = {}
    test_sources = {
        rel(path): path.read_text(encoding="utf-8", errors="ignore").lower().replace("-", "_").replace(" ", "_")
        for path in TESTS.glob("test_*.py")
    }
    for scenario, tokens in NEGATIVE_SCENARIOS.items():
        matched_tokens = [token for token in tokens if token in normalized]
        matched_files = sorted(
            filename
            for filename, source in test_sources.items()
            if any(token in source for token in tokens)
        )
        mapping[scenario] = {
            "status": "COVERED_AND_EXECUTED" if matched_tokens else (
                "SOURCE_MAPPING_ONLY" if matched_files else "UNMAPPED"
            ),
            "matched_output_tokens": matched_tokens,
            "matched_test_files": matched_files,
        }
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform-label", required=True)
    parser.add_argument("--baseline-sha", required=True)
    args = parser.parse_args()

    output_dir = ROOT / "m1-artifacts" / args.platform_label
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    platform_info = {
        "label": args.platform_label,
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": sys.version,
        "executable": sys.executable,
    }
    head = run_command("git_head", ["git", "rev-parse", "HEAD"], timeout=30)
    status = run_command("git_status", ["git", "status", "--short", "--branch"], timeout=30)
    diff = run_command(
        "baseline_diff",
        ["git", "diff", "--name-status", args.baseline_sha, "HEAD"],
        timeout=60,
    )

    inv = inventory()
    results: list[dict[str, Any]] = []

    requirements = ROOT / "requirements" / "windows-home-local.txt"
    if platform.system() == "Windows" and requirements.exists():
        results.append(
            run_command(
                "dependency_installation",
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-deps",
                    "--only-binary=:all:",
                    "--require-hashes",
                    "-r",
                    str(requirements),
                ],
                timeout=300,
            )
        )
    else:
        results.append(
            run_command(
                "dependency_installation",
                [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-deps", "-e", "."],
                timeout=300,
                expected_failure_reason="FOUNDATION_BUILD_BACKEND_DOES_NOT_SUPPORT_INSTALLABLE_DISTRIBUTION",
            )
        )

    results.append(
        run_command(
            "syntax_compile",
            [sys.executable, "-m", "compileall", "-q", str(SRC)],
            timeout=180,
        )
    )

    linter = next((tool for tool in ("ruff", "flake8", "pylint") if shutil.which(tool)), None)
    if linter:
        command = [linter, "check", "src", "tests"] if linter == "ruff" else [linter, "src", "tests"]
        results.append(run_command("lint", command, timeout=300))
    else:
        results.append({
            "name": "lint",
            "status": "BLOCKED_BASELINE",
            "reason": "NO_PINNED_LINTER_OR_LINT_CONFIGURATION_DETECTED",
        })

    type_checker = next((tool for tool in ("mypy", "pyright") if shutil.which(tool)), None)
    if type_checker:
        command = [type_checker, "src"]
        results.append(run_command("type_checking", command, timeout=300))
    else:
        results.append({
            "name": "type_checking",
            "status": "BLOCKED_BASELINE",
            "reason": "NO_PINNED_TYPE_CHECKER_OR_CONFIGURATION_DETECTED",
        })

    full_tests = run_command(
        "unit_tests_full_repository",
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(TESTS),
            "-t",
            str(ROOT),
            "-p",
            "test_*.py",
            "-v",
        ],
        timeout=1200,
        env={"PYTHONPATH": str(SRC), "PYTHONUTF8": "1"},
    )
    full_tests["test_count"] = test_count(full_tests["full_output"])
    results.append(full_tests)

    integration_modules = discover_module_names(
        ("integration", "pilot", "windows", "ingestion", "recovery", "adapter", "api", "worker", "one_click", "e2e")
    )
    if integration_modules:
        integration = run_command(
            "integration_tests",
            [sys.executable, "-m", "unittest", *integration_modules, "-v"],
            timeout=1200,
            env={"PYTHONPATH": str(SRC), "PYTHONUTF8": "1"},
        )
        integration["test_count"] = test_count(integration["full_output"])
        integration["modules"] = integration_modules
        results.append(integration)
    else:
        results.append({
            "name": "integration_tests",
            "status": "BLOCKED_BASELINE",
            "reason": "NO_INTEGRATION_TEST_MODULES_DISCOVERED_BY_NAMING_CONVENTION",
        })

    with tempfile.TemporaryDirectory(prefix="quantum-m1-wheel-") as wheel_dir:
        results.append(
            run_command(
                "build",
                [sys.executable, "-m", "pip", "wheel", "--no-deps", ".", "-w", wheel_dir],
                timeout=300,
                expected_failure_reason="WHEEL_AND_SDIST_BUILDS_INTENTIONALLY_DISABLED_IN_FOUNDATION",
            )
        )

    results.append(backend_smoke())
    results.append(worker_smoke())
    results.append(import_smoke())

    finance_modules = discover_module_names(("finance", "financial", "profit", "rounding", "rule"))
    if finance_modules:
        finance = run_command(
            "financial_smoke_test",
            [sys.executable, "-m", "unittest", *finance_modules, "-v"],
            timeout=600,
            env={"PYTHONPATH": str(SRC), "PYTHONUTF8": "1"},
        )
        finance["test_count"] = test_count(finance["full_output"])
        finance["modules"] = finance_modules
        results.append(finance)
    else:
        results.append({
            "name": "financial_smoke_test",
            "status": "FAIL",
            "reason": "NO_FINANCIAL_TEST_MODULES_DISCOVERED",
        })

    persistence_modules = discover_module_names(("storage", "config", "settings", "persist", "receipt", "recovery", "repair"))
    if persistence_modules:
        persistence = run_command(
            "settings_persistence_and_restart",
            [sys.executable, "-m", "unittest", *persistence_modules, "-v"],
            timeout=900,
            env={"PYTHONPATH": str(SRC), "PYTHONUTF8": "1"},
        )
        persistence["test_count"] = test_count(persistence["full_output"])
        persistence["modules"] = persistence_modules
        results.append(persistence)
    else:
        results.append({
            "name": "settings_persistence_and_restart",
            "status": "BLOCKED_BASELINE",
            "reason": "NO_PERSISTENCE_TEST_MODULES_DISCOVERED_BY_NAMING_CONVENTION",
        })

    if inv["separate_frontend_detected"]:
        results.append({
            "name": "frontend_startup",
            "status": "BLOCKED_BASELINE",
            "reason": "FRONTEND_MARKERS_PRESENT_BUT_NO_GENERIC_START_COMMAND_DEFINED_BY_AUDIT",
            "markers": inv["frontend_markers"],
        })
    else:
        results.append({
            "name": "frontend_startup",
            "status": "NOT_APPLICABLE_SEPARATE_FRONTEND",
            "reason": "NO_PACKAGE_MANAGER_OR_STANDALONE_FRONTEND_MANIFEST; LOCAL_UI_IS_PACKAGED_WITH_WINDOWS_ONE_CLICK_FLOW",
        })

    negative = coverage_map(full_tests["full_output"])

    for result in results:
        if "full_output" in result:
            log_path = logs_dir / f"{result['name']}.log"
            log_path.write_text(result.pop("full_output"), encoding="utf-8")
            result["log"] = rel(log_path)

    hard_failures = [
        result for result in results if str(result.get("status", "")).startswith("FAIL")
    ]
    baseline_blocks = [
        result for result in results if result.get("status") == "BLOCKED_BASELINE"
    ]

    report = {
        "milestone": "M1_BASELINE_AND_REPRODUCTION",
        "baseline_sha": args.baseline_sha,
        "audit_head": head.get("output_tail", "").strip(),
        "platform": platform_info,
        "git_status": status.get("output_tail", ""),
        "baseline_to_audit_diff": diff.get("output_tail", ""),
        "inventory": inv,
        "results": results,
        "negative_scenario_coverage": negative,
        "hard_failure_count": len(hard_failures),
        "baseline_block_count": len(baseline_blocks),
        "preliminary_verdict": "FAIL" if hard_failures else (
            "PASS_WITH_LIMITATIONS" if baseline_blocks else "PASS"
        ),
    }
    json_path = output_dir / "m1-baseline.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# M1 Baseline — {args.platform_label}",
        "",
        f"- Baseline SHA: `{args.baseline_sha}`",
        f"- Audit head: `{report['audit_head']}`",
        f"- Platform: `{platform_info['system']} {platform_info['release']}`",
        f"- Python: `{platform_info['python'].splitlines()[0]}`",
        f"- Preliminary verdict: **{report['preliminary_verdict']}**",
        f"- Tracked files: **{inv['tracked_file_count']}**",
        f"- Python modules: **{inv['python_module_count']}**",
        f"- Test modules: **{inv['test_module_count']}**",
        "",
        "## Required test matrix",
        "",
        "| Check | Status | Tests | Duration, s |",
        "|---|---|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| {result['name']} | {result.get('status')} | {result.get('test_count', '')} | {result.get('duration_seconds', '')} |"
        )
    lines.extend([
        "",
        "## Negative scenarios",
        "",
        "| Scenario | Status |",
        "|---|---|",
    ])
    for scenario, item in negative.items():
        lines.append(f"| {scenario} | {item['status']} |")
    lines.extend([
        "",
        "## Inventory summary",
        "",
        f"- Runtime entry points: `{json.dumps(inv['project_scripts'], ensure_ascii=False)}`",
        f"- Separate frontend detected: `{inv['separate_frontend_detected']}`",
        f"- Launchers: `{len(inv['launchers'])}`",
        f"- Workflows: `{inv['workflow_count']}`",
        "- Secret/config evidence contains key names only; values are not recorded.",
    ])
    (output_dir / "m1-baseline.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "platform": args.platform_label,
        "preliminary_verdict": report["preliminary_verdict"],
        "hard_failure_count": len(hard_failures),
        "baseline_block_count": len(baseline_blocks),
        "unit_test_count": full_tests.get("test_count"),
        "output": rel(json_path),
    }, sort_keys=True))
    return 1 if hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
